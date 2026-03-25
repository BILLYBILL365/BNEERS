import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
import fakeredis.aioredis as fakeredis
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.watchdog import WatchdogService

CRITICAL_AGENTS = ["cso", "cto", "cmo", "cfo", "coo"]


@pytest_asyncio.fixture
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


def _make_statuses(overdue_agents: list[str], timeout_seconds: int = 120) -> dict:
    now = datetime.now(timezone.utc)
    statuses = {}
    for agent_id in CRITICAL_AGENTS:
        if agent_id in overdue_agents:
            # Last seen more than timeout ago
            last_seen = now - timedelta(seconds=timeout_seconds + 10)
        else:
            last_seen = now  # healthy
        statuses[agent_id] = {"agent_id": agent_id, "status": "active", "last_seen": last_seen}
    return statuses


@pytest.mark.asyncio
async def test_healthy_agents_no_alert(bus):
    statuses = _make_statuses(overdue_agents=[])
    watchdog = WatchdogService(bus=bus, agent_statuses=statuses, timeout_seconds=120)
    await watchdog.check()
    # No alert events should be in the bus
    raw = await bus._redis.rpop(bus.CHANNEL)
    assert raw is None


@pytest.mark.asyncio
async def test_overdue_agent_triggers_alert(bus):
    statuses = _make_statuses(overdue_agents=["cso"])
    watchdog = WatchdogService(bus=bus, agent_statuses=statuses, timeout_seconds=120)
    await watchdog.check()

    alert_found = False
    for _ in range(10):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "agent.alert" and event.payload.get("agent_id") == "cso":
            alert_found = True
    assert alert_found


@pytest.mark.asyncio
async def test_agent_with_none_last_seen_not_flagged(bus):
    """Agents that have never sent a heartbeat (last_seen=None) are not flagged.
    They may not have started yet."""
    statuses = {"cso": {"agent_id": "cso", "status": "idle", "last_seen": None}}
    watchdog = WatchdogService(bus=bus, agent_statuses=statuses, timeout_seconds=120)
    await watchdog.check()
    raw = await bus._redis.rpop(bus.CHANNEL)
    assert raw is None


@pytest.mark.asyncio
async def test_multiple_overdue_agents_each_get_alert(bus):
    statuses = _make_statuses(overdue_agents=["cso", "cto"])
    watchdog = WatchdogService(bus=bus, agent_statuses=statuses, timeout_seconds=120)
    await watchdog.check()

    alerted = set()
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "agent.alert":
            alerted.add(event.payload.get("agent_id"))
    assert "cso" in alerted
    assert "cto" in alerted
