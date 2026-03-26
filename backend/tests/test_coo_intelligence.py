import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
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
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


@pytest.mark.asyncio
async def test_coo_tracks_task_dependencies(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    coo = COO(bus=bus, audit=audit)
    await coo.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_id": "t1", "depends_on": [], "task_type": "build_product"},
    ))
    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_id": "t2", "depends_on": ["t1"], "task_type": "launch_campaign"},
    ))
    for _ in range(20):
        await bus.process_one()

    assert "t1" in coo._task_graph
    assert "t2" in coo._task_graph
    assert "t1" in coo._task_graph["t2"]["depends_on"]


@pytest.mark.asyncio
async def test_coo_detects_deadlock_and_publishes_alert(bus, session_factory):
    """A → B → A circular dependency triggers a deadlock alert."""
    audit = AuditService(session_factory=session_factory)
    coo = COO(bus=bus, audit=audit)
    await coo.start()
    for _ in range(10):
        await bus.process_one()

    escalations = []
    await bus.subscribe("agent.escalation", lambda e: escalations.append(e))

    # Create A → B
    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_id": "tA", "depends_on": ["tB"], "task_type": "build"},
    ))
    # Create B → A (cycle)
    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_id": "tB", "depends_on": ["tA"], "task_type": "deploy"},
    ))
    for _ in range(20):
        await bus.process_one()

    assert len(escalations) >= 1
    assert "deadlock" in escalations[0].payload["reason"].lower()


@pytest.mark.asyncio
async def test_coo_removes_completed_tasks_from_graph(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    coo = COO(bus=bus, audit=audit)
    await coo.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_id": "t1", "depends_on": [], "task_type": "build"},
    ))
    for _ in range(10):
        await bus.process_one()

    assert "t1" in coo._task_graph

    await bus.publish(BusEvent(
        type="task.completed",
        payload={"task_id": "t1", "task_type": "build"},
    ))
    for _ in range(10):
        await bus.process_one()

    assert "t1" not in coo._task_graph
