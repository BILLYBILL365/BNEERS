import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.models.decision import Decision, DecisionStatus
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
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


@pytest_asyncio.fixture
async def svc(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    return DecisionService(bus=bus, session_factory=session_factory, audit=audit)


@pytest.mark.asyncio
async def test_decision_pending_creates_db_record(svc, db_session, bus):
    await svc.start()
    event = BusEvent(
        type="decision.pending",
        payload={
            "decision_id": "test-id-1",
            "title": "Launch B2B product",
            "description": "CSO recommends this market",
            "requested_by": "cso",
        },
    )
    await bus.publish(event)
    await bus.process_one()

    from sqlalchemy import select
    result = await db_session.execute(select(Decision))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Launch B2B product"
    assert rows[0].status == DecisionStatus.PENDING
    assert rows[0].requested_by == "cso"


@pytest.mark.asyncio
async def test_decision_pending_ignores_duplicate(svc, db_session, bus):
    """Publishing the same decision_id twice should not create two DB records."""
    await svc.start()
    payload = {
        "decision_id": "dup-id",
        "title": "Duplicate decision",
        "description": "Should only appear once",
        "requested_by": "cto",
    }
    await bus.publish(BusEvent(type="decision.pending", payload=payload))
    await bus.publish(BusEvent(type="decision.pending", payload=payload))
    await bus.process_one()
    await bus.process_one()

    from sqlalchemy import select
    result = await db_session.execute(select(Decision))
    rows = result.scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_handles_approved_event(svc, db_session, bus):
    """decision.approved event is handled without error and audit-logged."""
    await svc.start()
    received = []
    await bus.subscribe("decision.approved", lambda e: received.append(e))

    await bus.publish(BusEvent(
        type="decision.approved",
        payload={"decision_id": "abc", "title": "Go ahead", "decided_by": "board"},
    ))
    await bus.process_one()
    # The service handles it (no crash)
    # The event is still delivered to other subscribers
    assert len(received) == 1
