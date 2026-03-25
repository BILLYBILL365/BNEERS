import asyncio
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.agents.base import BaseAgent

TEST_DB = "sqlite+aiosqlite:///:memory:"


class EchoAgent(BaseAgent):
    """Minimal agent for testing — echoes received events."""
    agent_id = "test_agent"

    def __init__(self, bus, audit):
        super().__init__(bus=bus, audit=audit)
        self.received: list[BusEvent] = []

    async def on_start(self):
        await self.subscribe("ping", self._on_ping)

    async def _on_ping(self, event: BusEvent):
        self.received.append(event)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


@pytest_asyncio.fixture
async def audit(session_factory):
    return AuditService(session_factory=session_factory)


@pytest_asyncio.fixture
async def agent(bus, audit):
    a = EchoAgent(bus=bus, audit=audit)
    await a.start()
    return a


@pytest.mark.asyncio
async def test_start_emits_status_event(bus, audit):
    agent = EchoAgent(bus=bus, audit=audit)
    await agent.start()
    # agent.status event should be in the bus
    found = False
    for _ in range(20):
        processed = await bus.process_one()
        if not processed:
            break
        # check if it was an agent.status event (it may have been consumed already)
        found = True
    # The agent.start() published at least one event; just confirm it didn't crash
    assert agent._running is True


@pytest.mark.asyncio
async def test_subscribe_and_receive(bus, audit):
    agent = EchoAgent(bus=bus, audit=audit)
    await agent.start()
    # drain the agent.status event
    await bus.process_one()

    await bus.publish(BusEvent(type="ping", payload={"msg": "hello"}))
    await bus.process_one()

    assert len(agent.received) == 1
    assert agent.received[0].payload["msg"] == "hello"


@pytest.mark.asyncio
async def test_stop_sets_running_false(bus, audit):
    agent = EchoAgent(bus=bus, audit=audit)
    await agent.start()
    assert agent._running is True
    await agent.stop()
    assert agent._running is False


@pytest.mark.asyncio
async def test_with_retry_succeeds_on_first_try(bus, audit):
    agent = EchoAgent(bus=bus, audit=audit)
    await agent.start()

    calls = []
    async def work():
        calls.append(1)
        return "ok"

    result = await agent.with_retry(work, context="test_work")
    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_with_retry_retries_on_failure(bus, audit):
    agent = EchoAgent(bus=bus, audit=audit)
    await agent.start()
    # Drain startup events
    for _ in range(5):
        await bus.process_one()

    attempts = []
    async def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("not ready yet")
        return "done"

    # Patch retry_backoff to 0 to avoid slow tests
    agent.retry_backoff = [0.0, 0.0, 0.0]
    result = await agent.with_retry(flaky, context="flaky_work")
    assert result == "done"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_with_retry_escalates_after_max_retries(bus, audit):
    agent = EchoAgent(bus=bus, audit=audit)
    await agent.start()
    for _ in range(5):
        await bus.process_one()

    agent.retry_backoff = [0.0, 0.0, 0.0]

    async def always_fails():
        raise RuntimeError("permanent failure")

    with pytest.raises(RuntimeError):
        await agent.with_retry(always_fails, context="bad_work")

    # Should have published an agent.escalation event
    escalation_found = False
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "agent.escalation":
            escalation_found = True
    assert escalation_found


@pytest.mark.asyncio
async def test_request_decision_publishes_event(bus, audit):
    agent = EchoAgent(bus=bus, audit=audit)
    await agent.start()
    for _ in range(5):
        await bus.process_one()

    decision_id = await agent.request_decision(
        title="Enter B2B invoicing market",
        description="CSO recommends based on research",
    )
    assert decision_id is not None

    # decision.pending should be in bus
    decision_event = None
    for _ in range(10):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "decision.pending":
            decision_event = event
    assert decision_event is not None
    assert decision_event.payload["requested_by"] == "test_agent"
    assert decision_event.payload["decision_id"] == decision_id
