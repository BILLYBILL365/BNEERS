import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.agents.cso import CSO
from app.agents.cto import CTO
from app.agents.cmo import CMO
from app.agents.cfo import CFO
from app.agents.coo import COO

TEST_DB = "sqlite+aiosqlite:///:memory:"


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


@pytest.mark.asyncio
@pytest.mark.parametrize("AgentClass,expected_id", [
    (CSO, "cso"),
    (CTO, "cto"),
    (CMO, "cmo"),
    (CFO, "cfo"),
    (COO, "coo"),
])
async def test_agent_has_correct_id(AgentClass, expected_id, bus, audit):
    agent = AgentClass(bus=bus, audit=audit)
    assert agent.agent_id == expected_id


@pytest.mark.asyncio
@pytest.mark.parametrize("AgentClass", [CSO, CTO, CMO, CFO, COO])
async def test_agent_starts_without_error(AgentClass, bus, audit):
    agent = AgentClass(bus=bus, audit=audit)
    await agent.start()
    assert agent._running is True


@pytest.mark.asyncio
@pytest.mark.parametrize("AgentClass", [CSO, CTO, CMO, CFO, COO])
async def test_agent_emits_status_on_start(AgentClass, bus, audit):
    agent = AgentClass(bus=bus, audit=audit)
    await agent.start()

    status_found = False
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "agent.status" and event.payload.get("agent_id") == agent.agent_id:
            status_found = True
    assert status_found


@pytest.mark.asyncio
async def test_cso_subscribes_to_decision_events(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    # CSO should have handlers registered for decision.approved and decision.rejected
    assert "decision.approved" in bus._handlers
    assert "decision.rejected" in bus._handlers


@pytest.mark.asyncio
async def test_cfo_subscribes_to_task_events(bus, audit):
    cfo = CFO(bus=bus, audit=audit)
    await cfo.start()
    assert "task.completed" in bus._handlers


@pytest.mark.asyncio
async def test_agent_stops_cleanly(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    await cso.stop()
    assert cso._running is False
