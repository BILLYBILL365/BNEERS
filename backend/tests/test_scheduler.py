import asyncio
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.scheduler import AgentScheduler, get_scheduler, set_scheduler

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


@pytest_asyncio.fixture
async def scheduler(bus, audit):
    s = AgentScheduler(bus=bus, audit=audit, interval_seconds=3600)
    await s.start()
    yield s
    await s.stop()


async def test_trigger_starts_cycle(scheduler, bus):
    started = await scheduler.trigger()
    assert started is True
    assert scheduler._cycle_running is True
    assert scheduler._current_cycle_id is not None
    # Verify cycle.start event published
    raw = await bus._redis.rpop(bus.CHANNEL)
    event = BusEvent.model_validate_json(raw)
    assert event.type == "cycle.start"
    assert event.payload["cycle_id"] == scheduler._current_cycle_id


async def test_trigger_skips_when_running(scheduler, bus):
    await scheduler.trigger()
    # drain the bus
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    started = await scheduler.trigger()
    assert started is False
    assert scheduler._cycle_running is True
    # No new event published
    assert await bus._redis.rpop(bus.CHANNEL) is None


async def test_trigger_logs_cycle_started(scheduler, audit, session_factory):
    await scheduler.trigger()
    from app.models.audit_log import AuditLog
    from sqlalchemy import select
    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.event_type == "cycle_started")
        )
        logs = result.scalars().all()
    assert len(logs) == 1


async def test_trigger_skipped_logs_cycle_skipped(scheduler, session_factory):
    await scheduler.trigger()
    await scheduler.trigger()
    from app.models.audit_log import AuditLog
    from sqlalchemy import select
    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.event_type == "cycle_skipped")
        )
        logs = result.scalars().all()
    assert len(logs) == 1


async def test_on_cycle_completed_resets_state(scheduler, bus):
    await scheduler.trigger()
    cycle_id = scheduler._current_cycle_id
    # Drain the cycle.start event published by trigger()
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    # Simulate CMO publishing cycle.completed
    event = BusEvent(type="cycle.completed", payload={"cycle_id": cycle_id, "outcome": "sent"})
    await bus.publish(event)
    await bus.process_one()
    assert scheduler._cycle_running is False
    assert scheduler._current_cycle_id is None


async def test_on_cycle_completed_ignores_wrong_cycle_id(scheduler, bus):
    await scheduler.trigger()
    # Drain the cycle.start event published by trigger()
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    # Simulate a stale cycle.completed from a different cycle
    event = BusEvent(type="cycle.completed", payload={"cycle_id": "wrong-id", "outcome": "sent"})
    await bus.publish(event)
    await bus.process_one()
    assert scheduler._cycle_running is True  # unchanged


async def test_on_cycle_completed_cancels_timeout(scheduler, bus):
    await scheduler.trigger()
    cycle_id = scheduler._current_cycle_id
    timeout_task = scheduler._timeout_task
    assert timeout_task is not None
    assert not timeout_task.done()
    # Drain the cycle.start event published by trigger()
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    event = BusEvent(type="cycle.completed", payload={"cycle_id": cycle_id, "outcome": "sent"})
    await bus.publish(event)
    await bus.process_one()
    await asyncio.sleep(0)  # let cancellation propagate
    assert timeout_task.cancelled() or timeout_task.done()


async def test_on_cycle_completed_with_no_timeout_task(scheduler, bus):
    """No crash when _timeout_task is None."""
    await scheduler.trigger()
    cycle_id = scheduler._current_cycle_id
    scheduler._timeout_task = None  # force None
    # Drain the cycle.start event published by trigger()
    while await bus._redis.rpop(bus.CHANNEL):
        pass
    event = BusEvent(type="cycle.completed", payload={"cycle_id": cycle_id, "outcome": "sent"})
    await bus.publish(event)
    await bus.process_one()  # must not raise
    assert scheduler._cycle_running is False


async def test_on_timeout_resets_state_and_publishes_alert(bus, audit):
    scheduler = AgentScheduler(bus=bus, audit=audit, interval_seconds=3600)
    scheduler._cycle_running = True
    scheduler._current_cycle_id = "cycle-timeout-test"
    with patch("app.scheduler.asyncio.sleep", new=AsyncMock(return_value=None)):
        await scheduler._on_timeout()
    assert scheduler._cycle_running is False
    assert scheduler._current_cycle_id is None
    assert scheduler._timeout_task is None
    # Verify agent.alert published
    raw = await bus._redis.rpop(bus.CHANNEL)
    event = BusEvent.model_validate_json(raw)
    assert event.type == "agent.alert"
    assert event.payload["reason"] == "cycle_timeout"


async def test_on_timeout_guard_when_not_running(bus, audit):
    """_on_timeout does nothing if _cycle_running is already False."""
    scheduler = AgentScheduler(bus=bus, audit=audit, interval_seconds=3600)
    scheduler._cycle_running = False
    with patch("app.scheduler.asyncio.sleep", new=AsyncMock(return_value=None)):
        await scheduler._on_timeout()
    # No alert published
    assert await bus._redis.rpop(bus.CHANNEL) is None


async def test_loop_exception_caught_loop_continues(bus, audit):
    """Exception in trigger() is caught; loop does not crash."""
    scheduler = AgentScheduler(bus=bus, audit=audit, interval_seconds=0)
    call_count = 0

    async def fake_trigger():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        return False

    scheduler.trigger = fake_trigger
    loop_task = asyncio.create_task(scheduler._loop())
    await asyncio.sleep(0.05)  # let loop tick twice
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    assert call_count >= 2  # loop continued after exception


async def test_singleton_set_and_get(bus, audit):
    s = AgentScheduler(bus=bus, audit=audit, interval_seconds=3600)
    set_scheduler(s)
    assert get_scheduler() is s
    set_scheduler(None)
    assert get_scheduler() is None
