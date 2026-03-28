import asyncio
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.runner import AgentRunner

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
async def runner(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    r = AgentRunner(bus=bus, audit=audit)
    return r


@pytest.mark.asyncio
async def test_runner_starts_all_csuite_agents(runner):
    await runner.start()
    assert len(runner.agents) == 4
    agent_ids = {a.agent_id for a in runner.agents.values()}
    assert agent_ids == {"cso", "cmo", "cfo", "coo"}
    assert all(a._running for a in runner.agents.values())
    await runner.stop()


@pytest.mark.asyncio
async def test_runner_stop_stops_all_agents(runner):
    await runner.start()
    await runner.stop()
    assert all(not a._running for a in runner.agents.values())


@pytest.mark.asyncio
async def test_agent_status_event_updates_status_store(runner, bus):
    status_store: dict = {}
    runner.status_store = status_store

    await runner.start()

    # Drain startup events
    for _ in range(50):
        processed = await bus.process_one()
        if not processed:
            break

    # All agents should have emitted agent.status on start
    assert "cso" in status_store
    assert status_store["cso"]["status"] in ("active", "idle")

    await runner.stop()


@pytest.mark.asyncio
async def test_runner_heartbeat_updates_all_agents(runner, bus):
    status_store: dict = {}
    runner.status_store = status_store

    await runner.start()
    for _ in range(50):
        if not await bus.process_one():
            break

    await runner.heartbeat_all()
    for _ in range(50):
        if not await bus.process_one():
            break

    for agent_id in ["cso", "cmo", "cfo", "coo"]:
        assert agent_id in status_store

    await runner.stop()


@pytest.mark.asyncio
async def test_runner_creates_agents_with_no_llm_when_key_missing(bus, session_factory):
    """Runner starts all agents even when ANTHROPIC_API_KEY is empty (no-op LLM)."""
    audit = AuditService(session_factory=session_factory)
    runner = AgentRunner(bus=bus, audit=audit, anthropic_api_key="")
    status_store: dict = {}
    runner.status_store = status_store
    await runner.start()
    for agent_id in ["cso", "cmo", "cfo", "coo"]:
        assert agent_id in runner.agents
    await runner.stop()
