from __future__ import annotations

from datetime import datetime, timezone

from app.redis_bus import RedisBus
from app.schemas.events import BusEvent

# Only C-Suite agents are critical — workers going down is a degraded-mode event, not an alert
CRITICAL_AGENTS = ["cso", "cto", "cmo", "cfo", "coo"]


class WatchdogService:
    def __init__(
        self,
        bus: RedisBus,
        agent_statuses: dict,
        timeout_seconds: int = 120,
    ) -> None:
        self._bus = bus
        self._agent_statuses = agent_statuses
        self._timeout = timeout_seconds

    async def check(self) -> list[str]:
        """Check all critical agents. Returns list of overdue agent IDs."""
        now = datetime.now(timezone.utc)
        overdue: list[str] = []

        for agent_id in CRITICAL_AGENTS:
            entry = self._agent_statuses.get(agent_id)
            if not entry:
                continue
            last_seen = entry.get("last_seen")
            if last_seen is None:
                continue  # Never sent heartbeat — may not have started yet
            if (now - last_seen).total_seconds() > self._timeout:
                overdue.append(agent_id)
                await self._bus.publish(BusEvent(
                    type="agent.alert",
                    payload={
                        "agent_id": agent_id,
                        "reason": "heartbeat_overdue",
                        "last_seen": last_seen.isoformat(),
                        "timeout_seconds": self._timeout,
                    },
                ))

        return overdue
