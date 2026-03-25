"""
Full Phase 2 integration test: agents start → CSO requests a decision →
DecisionService creates DB record → board approves → decision.approved
event fires → CSO's handler runs → audit log has complete trail.
"""
import asyncio
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.models.audit_log import AuditLog
from app.models.decision import Decision, DecisionStatus
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.services.decisions import DecisionService
from app.services.watchdog import WatchdogService
from app.runner import AgentRunner

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    e = create_async_engine(TEST_DB)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await e.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


@pytest.mark.asyncio
async def test_full_decision_lifecycle(bus, session_factory, db_session):
    """CSO requests decision → DB record created → approved → audit trail complete."""
    audit = AuditService(session_factory=session_factory)
    decision_svc = DecisionService(bus=bus, session_factory=session_factory, audit=audit)
    runner = AgentRunner(bus=bus, audit=audit)
    status_store: dict = {}
    runner.status_store = status_store

    # Start everything
    await decision_svc.start()
    await runner.start()

    # CSO requests a decision
    cso = runner.agents["cso"]
    decision_id = await cso.request_decision(
        title="Enter B2B invoicing market",
        description="Strong demand, low competition",
    )

    # Process bus events (decision.pending → DecisionService creates DB record)
    for _ in range(50):
        if not await bus.process_one():
            break

    # Verify DB record was created
    decision = await db_session.get(Decision, decision_id)
    assert decision is not None
    assert decision.status == DecisionStatus.PENDING
    assert decision.requested_by == "cso"

    # Simulate Board approving (publish decision.approved event)
    await bus.publish(BusEvent(
        type="decision.approved",
        payload={"decision_id": decision_id, "title": decision.title, "decided_by": "board"},
    ))

    # Process approval
    for _ in range(50):
        if not await bus.process_one():
            break

    # Verify audit log has the full trail
    result = await db_session.execute(select(AuditLog).order_by(AuditLog.timestamp))
    logs = result.scalars().all()
    event_types = [log.event_type for log in logs]

    assert "agent_started" in event_types  # CSO started
    assert "decision.pending" in event_types  # CSO requested decision
    assert "decision.approved" in event_types  # CSO acknowledged approval

    await runner.stop()


@pytest.mark.asyncio
async def test_watchdog_detects_overdue_agent(bus, db_session):
    """Watchdog fires agent.alert if an agent's heartbeat is overdue."""
    from datetime import datetime, timezone, timedelta

    status_store = {
        "cso": {"agent_id": "cso", "status": "active",
                "last_seen": datetime.now(timezone.utc) - timedelta(seconds=200)},
    }
    watchdog = WatchdogService(bus=bus, agent_statuses=status_store, timeout_seconds=120)
    await watchdog.check()

    alerts = []
    for _ in range(10):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "agent.alert":
            alerts.append(event)

    assert len(alerts) == 1
    assert alerts[0].payload["agent_id"] == "cso"
    assert alerts[0].payload["reason"] == "heartbeat_overdue"


@pytest.mark.asyncio
async def test_all_csuite_agents_heartbeat(bus, session_factory):
    """All 5 C-Suite agents heartbeat and update status store."""
    audit = AuditService(session_factory=session_factory)
    runner = AgentRunner(bus=bus, audit=audit)
    status_store: dict = {}
    runner.status_store = status_store

    await runner.start()
    await runner.heartbeat_all()

    for _ in range(100):
        if not await bus.process_one():
            break

    for agent_id in ["cso", "cto", "cmo", "cfo", "coo"]:
        assert agent_id in status_store, f"{agent_id} not in status store"
        assert status_store[agent_id]["last_seen"] is not None

    await runner.stop()
