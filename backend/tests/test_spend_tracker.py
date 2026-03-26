import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.spend_tracker import SpendTracker, SpendCategory


@pytest_asyncio.fixture
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


@pytest.mark.asyncio
async def test_record_spend_under_cap(bus):
    tracker = SpendTracker(bus=bus, daily_cap_ads=100.0, daily_cap_apis=50.0)
    exceeded = await tracker.record("ads", 40.0)
    assert exceeded is False
    assert tracker.daily_total("ads") == 40.0


@pytest.mark.asyncio
async def test_record_spend_hits_daily_hard_cap(bus):
    tracker = SpendTracker(bus=bus, daily_cap_ads=100.0, daily_cap_apis=50.0)
    exceeded = await tracker.record("ads", 101.0)
    assert exceeded is True


@pytest.mark.asyncio
async def test_hard_cap_publishes_spend_exceeded_event(bus):
    tracker = SpendTracker(bus=bus, daily_cap_ads=100.0, daily_cap_apis=50.0)
    await tracker.record("ads", 150.0)
    raw = await bus._redis.rpop(bus.CHANNEL)
    assert raw is not None
    event = BusEvent.model_validate_json(raw)
    assert event.type == "spend.exceeded"
    assert event.payload["category"] == "ads"
    assert event.payload["amount"] == 150.0


@pytest.mark.asyncio
async def test_reset_clears_daily_totals(bus):
    tracker = SpendTracker(bus=bus, daily_cap_ads=100.0, daily_cap_apis=50.0)
    await tracker.record("ads", 80.0)
    tracker.reset_daily()
    assert tracker.daily_total("ads") == 0.0


@pytest.mark.asyncio
async def test_multiple_records_accumulate(bus):
    tracker = SpendTracker(bus=bus, daily_cap_ads=100.0, daily_cap_apis=50.0)
    await tracker.record("ads", 30.0)
    await tracker.record("ads", 30.0)
    assert tracker.daily_total("ads") == 60.0
    exceeded = await tracker.record("ads", 50.0)
    assert exceeded is True  # 110 > 100
