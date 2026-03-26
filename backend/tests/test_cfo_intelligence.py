import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.services.spend_tracker import SpendTracker
from app.agents.cfo import CFO

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
async def test_cfo_requests_decision_when_weekly_soft_cap_exceeded(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    spend_tracker = SpendTracker(bus=bus, daily_cap_ads=1000.0, daily_cap_apis=500.0)
    cfo = CFO(bus=bus, audit=audit, spend_tracker=spend_tracker, weekly_soft_cap=500.0)
    await cfo.start()
    for _ in range(10):
        await bus.process_one()

    pending_decisions = []
    await bus.subscribe("decision.pending", lambda e: pending_decisions.append(e))

    await bus.publish(BusEvent(
        type="revenue.updated",
        payload={"weekly_revenue": 10_000.0, "total_weekly_spend": 600.0},
    ))
    for _ in range(30):
        await bus.process_one()

    assert len(pending_decisions) > 0
    assert any(
        "spend" in e.payload.get("title", "").lower() or "cap" in e.payload.get("title", "").lower()
        for e in pending_decisions
    )


@pytest.mark.asyncio
async def test_cfo_no_decision_when_spend_under_cap(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    spend_tracker = SpendTracker(bus=bus, daily_cap_ads=1000.0, daily_cap_apis=500.0)
    cfo = CFO(bus=bus, audit=audit, spend_tracker=spend_tracker, weekly_soft_cap=500.0)
    await cfo.start()
    for _ in range(10):
        await bus.process_one()

    pending_decisions = []
    await bus.subscribe("decision.pending", lambda e: pending_decisions.append(e))

    await bus.publish(BusEvent(
        type="revenue.updated",
        payload={"weekly_revenue": 5_000.0, "total_weekly_spend": 200.0},
    ))
    for _ in range(20):
        await bus.process_one()

    assert len(pending_decisions) == 0


@pytest.mark.asyncio
async def test_cfo_audit_logs_revenue_event(bus, session_factory):
    from sqlalchemy import select
    from app.models.audit_log import AuditLog
    audit = AuditService(session_factory=session_factory)
    spend_tracker = SpendTracker(bus=bus, daily_cap_ads=1000.0, daily_cap_apis=500.0)
    cfo = CFO(bus=bus, audit=audit, spend_tracker=spend_tracker, weekly_soft_cap=500.0)
    await cfo.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="revenue.updated",
        payload={"weekly_revenue": 5_000.0, "total_weekly_spend": 100.0},
    ))
    for _ in range(20):
        await bus.process_one()

    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.event_type == "revenue.updated")
        )
        logs = result.scalars().all()
    assert len(logs) >= 1
    assert logs[0].payload["weekly_revenue"] == 5_000.0
