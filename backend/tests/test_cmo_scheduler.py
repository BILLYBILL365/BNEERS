import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.agents.cmo import CMO

TEST_DB = "sqlite+aiosqlite:///:memory:"

SAMPLE_LEADS = [
    {"name": "ACME Plumbing", "city": "Atlanta, GA", "niche": "plumbing", "score": 90},
    {"name": "Best HVAC", "city": "Dallas, TX", "niche": "hvac", "score": 85},
]


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


async def test_cmo_subscribes_to_leads_approved(bus, audit):
    cmo = CMO(bus=bus, audit=audit)
    await cmo.start()
    assert "leads.approved" in bus._handlers
    assert "decision.approved" in bus._handlers
    assert "decision.rejected" in bus._handlers


async def test_leads_approved_triggers_draft_outreach(bus, audit):
    cmo = CMO(bus=bus, audit=audit)
    await cmo.start()
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="leads.approved", payload={
        "cycle_id": "cycle-001",
        "leads": SAMPLE_LEADS,
    }))
    await bus.process_one()
    # Should have posted decision.pending for outreach approval
    found = False
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        e = BusEvent.model_validate_json(raw)
        if e.type == "decision.pending" and "outreach" in e.payload.get("title", "").lower():
            assert e.payload.get("cycle_id") == "cycle-001"
            found = True
    assert found, "CMO should post decision.pending with outreach drafts"


async def test_leads_approved_ignored_when_outreach_active(bus, audit):
    cmo = CMO(bus=bus, audit=audit)
    await cmo.start()
    cmo._current_cycle_id = "cycle-ACTIVE"
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="leads.approved", payload={
        "cycle_id": "cycle-NEW",
        "leads": SAMPLE_LEADS,
    }))
    await bus.process_one()
    raw = await bus._redis.rpop(bus.CHANNEL)
    if raw is not None:
        e = BusEvent.model_validate_json(raw)
        assert e.type != "decision.pending"
    assert cmo._current_cycle_id == "cycle-ACTIVE"


async def test_outreach_approved_publishes_cycle_completed_sent(bus, audit):
    cmo = CMO(bus=bus, audit=audit)
    await cmo.start()
    cmo._current_cycle_id = "cycle-001"
    cmo._pending_drafts = [{"to": "a@b.com", "subject": "Hi", "body": "Test"}]
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="decision.approved", payload={
        "decision_id": "d-1",
        "title": "Outreach drafts ready",
        "decided_by": "board",
        "cycle_id": "cycle-001",
    }))
    await bus.process_one()
    found = False
    for _ in range(30):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        e = BusEvent.model_validate_json(raw)
        if e.type == "cycle.completed":
            assert e.payload["cycle_id"] == "cycle-001"
            assert e.payload["outcome"] == "sent"
            found = True
    assert found, "CMO should publish cycle.completed {sent} on outreach approval"
    assert cmo._current_cycle_id is None


async def test_outreach_rejected_publishes_cycle_completed_rejected(bus, audit):
    cmo = CMO(bus=bus, audit=audit)
    await cmo.start()
    cmo._current_cycle_id = "cycle-001"
    cmo._pending_drafts = [{"to": "a@b.com", "subject": "Hi", "body": "Test"}]
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="decision.rejected", payload={
        "decision_id": "d-1",
        "title": "Outreach drafts ready",
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
    assert found, "CMO should publish cycle.completed {rejected} on outreach rejection"
    assert cmo._current_cycle_id is None


async def test_decision_with_wrong_cycle_id_ignored_by_cmo(bus, audit):
    cmo = CMO(bus=bus, audit=audit)
    await cmo.start()
    cmo._current_cycle_id = "cycle-001"
    cmo._pending_drafts = [{"to": "a@b.com", "subject": "Hi", "body": "Test"}]
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    await bus.publish(BusEvent(type="decision.approved", payload={
        "decision_id": "d-1",
        "decided_by": "board",
        "cycle_id": "cycle-WRONG",
    }))
    await bus.process_one()
    raw = await bus._redis.rpop(bus.CHANNEL)
    if raw is not None:
        e = BusEvent.model_validate_json(raw)
        assert e.type != "cycle.completed"
    assert cmo._current_cycle_id == "cycle-001"  # unchanged
