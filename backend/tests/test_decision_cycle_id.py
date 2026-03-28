import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.models.decision import Decision
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.services.decisions import DecisionService

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


async def test_decision_stores_cycle_id(session_factory):
    async with session_factory() as session:
        d = Decision(
            title="Test", description="Test desc",
            requested_by="cso", cycle_id="cycle-abc"
        )
        session.add(d)
        await session.commit()
        await session.refresh(d)
    assert d.cycle_id == "cycle-abc"


async def test_decision_cycle_id_defaults_none(session_factory):
    async with session_factory() as session:
        d = Decision(title="Test", description="Test desc", requested_by="cso")
        session.add(d)
        await session.commit()
        await session.refresh(d)
    assert d.cycle_id is None


async def test_on_pending_stores_cycle_id(bus, audit, session_factory):
    service = DecisionService(bus=bus, session_factory=session_factory, audit=audit)
    await service.start()
    event = BusEvent(type="decision.pending", payload={
        "decision_id": "d-cycle-1",
        "title": "Lead list ready",
        "description": "5 leads found",
        "requested_by": "cso",
        "cycle_id": "cycle-xyz",
    })
    await bus.publish(event)
    await bus.process_one()
    async with session_factory() as session:
        decision = await session.get(Decision, "d-cycle-1")
    assert decision is not None
    assert decision.cycle_id == "cycle-xyz"


async def test_on_pending_without_cycle_id(bus, audit, session_factory):
    service = DecisionService(bus=bus, session_factory=session_factory, audit=audit)
    await service.start()
    event = BusEvent(type="decision.pending", payload={
        "decision_id": "d-no-cycle",
        "title": "Manual decision",
        "description": "No cycle",
        "requested_by": "board",
    })
    await bus.publish(event)
    await bus.process_one()
    async with session_factory() as session:
        decision = await session.get(Decision, "d-no-cycle")
    assert decision is not None
    assert decision.cycle_id is None


async def test_approved_event_includes_cycle_id(bus, audit, session_factory):
    """Decision with cycle_id: router publishes cycle_id in decision.approved event."""
    # Pre-seed a decision with cycle_id in DB
    async with session_factory() as session:
        d = Decision(
            id="d-approve-cycle",
            title="Lead list",
            description="5 leads",
            requested_by="cso",
            cycle_id="cycle-approve",
        )
        session.add(d)
        await session.commit()
    # Simulate what the router does on approve: read decision, build payload, publish
    async with session_factory() as session:
        decision = await session.get(Decision, "d-approve-cycle")
    payload = {"decision_id": decision.id, "title": decision.title, "decided_by": "board"}
    if decision.cycle_id:
        payload["cycle_id"] = decision.cycle_id
    await bus.publish(BusEvent(type="decision.approved", payload=payload))
    raw = await bus._redis.rpop(bus.CHANNEL)
    event = BusEvent.model_validate_json(raw)
    assert event.type == "decision.approved"
    assert event.payload.get("cycle_id") == "cycle-approve"


async def test_approved_event_no_cycle_id_when_not_set(bus, audit, session_factory):
    async with session_factory() as session:
        d = Decision(
            id="d-approve-plain",
            title="Plain decision",
            description="No cycle",
            requested_by="board",
        )
        session.add(d)
        await session.commit()
    async with session_factory() as session:
        decision = await session.get(Decision, "d-approve-plain")
    payload = {"decision_id": decision.id, "title": decision.title, "decided_by": "board"}
    if decision.cycle_id:
        payload["cycle_id"] = decision.cycle_id
    await bus.publish(BusEvent(type="decision.approved", payload=payload))
    raw = await bus._redis.rpop(bus.CHANNEL)
    event = BusEvent.model_validate_json(raw)
    assert "cycle_id" not in event.payload
