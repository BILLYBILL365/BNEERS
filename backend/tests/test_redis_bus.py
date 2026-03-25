import pytest
import fakeredis.aioredis as fakeredis
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent

@pytest.fixture
async def bus():
    fake_redis = fakeredis.FakeRedis()
    return RedisBus(redis_client=fake_redis)

@pytest.mark.asyncio
async def test_publish_and_subscribe(bus):
    received = []

    async def handler(event: BusEvent):
        received.append(event)

    await bus.subscribe("task.created", handler)

    event = BusEvent(type="task.created", payload={"task_id": "123", "agent_id": "cto"})
    await bus.publish(event)
    await bus.process_one()

    assert len(received) == 1
    assert received[0].type == "task.created"
    assert received[0].payload["task_id"] == "123"

@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    calls_a = []
    calls_b = []

    await bus.subscribe("revenue.updated", lambda e: calls_a.append(e))
    await bus.subscribe("revenue.updated", lambda e: calls_b.append(e))

    event = BusEvent(type="revenue.updated", payload={"amount": 5000})
    await bus.publish(event)
    await bus.process_one()

    assert len(calls_a) == 1
    assert len(calls_b) == 1

@pytest.mark.asyncio
async def test_unsubscribed_channel_not_received(bus):
    received = []
    await bus.subscribe("task.created", lambda e: received.append(e))

    event = BusEvent(type="decision.pending", payload={"decision_id": "abc"})
    await bus.publish(event)
    await bus.process_one()

    assert len(received) == 0
