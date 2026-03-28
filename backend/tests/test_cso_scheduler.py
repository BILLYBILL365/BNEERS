import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.agents.cso import CSO

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


@pytest_asyncio.fixture
async def audit(session_factory):
    return AuditService(session_factory=session_factory)


async def test_cso_subscribes_to_cycle_start(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    assert "cycle.start" in bus._handlers
    assert "decision.approved" in bus._handlers
    assert "decision.rejected" in bus._handlers


async def test_cycle_start_triggers_lead_research(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    # Drain agent.status event
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    event = BusEvent(type="cycle.start", payload={"cycle_id": "cycle-001"})
    await bus.publish(event)
    await bus.process_one()
    # Should have published decision.pending for lead approval
    found = False
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        e = BusEvent.model_validate_json(raw)
        if e.type == "decision.pending" and "lead list" in e.payload.get("title", "").lower():
            assert e.payload.get("cycle_id") == "cycle-001"
            found = True
    assert found, "CSO should post decision.pending with lead list"


async def test_cycle_start_ignored_when_already_active(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    # Start first cycle
    await bus.publish(BusEvent(type="cycle.start", payload={"cycle_id": "cycle-A"}))
    await bus.process_one()
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    # Start second cycle — should be ignored
    await bus.publish(BusEvent(type="cycle.start", payload={"cycle_id": "cycle-B"}))
    await bus.process_one()
    # No new decision.pending
    raw = await bus._redis.rpop(bus.CHANNEL)
    if raw is not None:
        e = BusEvent.model_validate_json(raw)
        assert e.type != "decision.pending", "Duplicate cycle.start should be ignored"
    assert cso._current_cycle_id == "cycle-A"


async def test_decision_approved_with_matching_cycle_id_publishes_leads_approved(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    cso._current_cycle_id = "cycle-001"
    cso._pending_leads = [{"name": "ACME Plumbing", "city": "Atlanta", "score": 90}]
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="decision.approved", payload={
        "decision_id": "d-1",
        "title": "Lead list ready",
        "decided_by": "board",
        "cycle_id": "cycle-001",
    }))
    await bus.process_one()
    found = False
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        e = BusEvent.model_validate_json(raw)
        if e.type == "leads.approved":
            assert e.payload["cycle_id"] == "cycle-001"
            assert len(e.payload["leads"]) == 1
            found = True
    assert found, "CSO should publish leads.approved on approval"
    assert cso._current_cycle_id is None
    assert cso._pending_leads == []


async def test_decision_approved_with_wrong_cycle_id_ignored(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    cso._current_cycle_id = "cycle-001"
    cso._pending_leads = [{"name": "ACME", "score": 90}]
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="decision.approved", payload={
        "decision_id": "d-1",
        "title": "Other decision",
        "decided_by": "board",
        "cycle_id": "cycle-WRONG",
    }))
    await bus.process_one()
    # No leads.approved published
    raw = await bus._redis.rpop(bus.CHANNEL)
    if raw is not None:
        e = BusEvent.model_validate_json(raw)
        assert e.type != "leads.approved"
    assert cso._current_cycle_id == "cycle-001"  # unchanged


async def test_decision_rejected_with_matching_cycle_id_publishes_cycle_completed(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    cso._current_cycle_id = "cycle-001"
    cso._pending_leads = [{"name": "ACME", "score": 90}]
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="decision.rejected", payload={
        "decision_id": "d-1",
        "title": "Lead list ready",
        "decided_by": "board",
        "cycle_id": "cycle-001",
    }))
    await bus.process_one()
    found = False
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        e = BusEvent.model_validate_json(raw)
        if e.type == "cycle.completed":
            assert e.payload["cycle_id"] == "cycle-001"
            assert e.payload["outcome"] == "rejected"
            found = True
    assert found, "CSO should publish cycle.completed on rejection"
    assert cso._current_cycle_id is None


async def test_decision_rejected_with_wrong_cycle_id_ignored(bus, audit):
    cso = CSO(bus=bus, audit=audit)
    await cso.start()
    cso._current_cycle_id = "cycle-001"
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="decision.rejected", payload={
        "decision_id": "d-1",
        "decided_by": "board",
        "cycle_id": "cycle-WRONG",
    }))
    await bus.process_one()
    raw = await bus._redis.rpop(bus.CHANNEL)
    if raw is not None:
        e = BusEvent.model_validate_json(raw)
        assert e.type != "cycle.completed"
    assert cso._current_cycle_id == "cycle-001"  # unchanged
