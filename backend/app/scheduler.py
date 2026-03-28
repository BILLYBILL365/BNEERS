from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService

_scheduler: "AgentScheduler | None" = None


def set_scheduler(scheduler: "AgentScheduler | None") -> None:
    global _scheduler
    _scheduler = scheduler


def get_scheduler() -> "AgentScheduler | None":
    return _scheduler


class AgentScheduler:
    """Fires a business cycle every interval_seconds and tracks cycle state.

    Publishes cycle.start to kick off the CSO → CMO pipeline.
    Listens for cycle.completed to reset state.
    Maintains a 4-hour timeout safety reset.
    """

    def __init__(self, bus: RedisBus, audit: AuditService, interval_seconds: int) -> None:
        self._bus = bus
        self._audit = audit
        self._interval = interval_seconds
        self._cycle_running: bool = False
        self._current_cycle_id: str | None = None
        self._loop_task: asyncio.Task | None = None
        self._timeout_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._bus.subscribe("cycle.completed", self._on_cycle_completed)
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

    async def trigger(self) -> bool:
        """Start a new cycle. Returns True if started, False if already running."""
        if self._cycle_running:
            await self._audit.log(
                agent_id="scheduler",
                event_type="cycle_skipped",
                payload={"reason": "cycle already running"},
            )
            return False
        self._cycle_running = True
        self._current_cycle_id = str(uuid.uuid4())
        self._timeout_task = asyncio.create_task(self._on_timeout())
        await self._bus.publish(BusEvent(
            type="cycle.start",
            payload={"cycle_id": self._current_cycle_id},
        ))
        await self._audit.log(
            agent_id="scheduler",
            event_type="cycle_started",
            payload={"cycle_id": self._current_cycle_id},
        )
        return True

    async def _loop(self) -> None:
        """Sleep then trigger, forever. First cycle fires after first full interval."""
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.trigger()
            except Exception as exc:
                await self._audit.log(
                    agent_id="scheduler",
                    event_type="cycle_error",
                    payload={"error": str(exc)},
                    outcome="error",
                )

    async def _on_cycle_completed(self, event: BusEvent) -> None:
        if not self._cycle_running:
            return
        if event.payload.get("cycle_id") != self._current_cycle_id:
            return
        # Cancel timeout synchronously before any await
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None
        self._cycle_running = False
        self._current_cycle_id = None
        await self._audit.log(
            agent_id="scheduler",
            event_type="cycle_completed",
            payload=event.payload,
            outcome=event.payload.get("outcome"),
        )

    async def _on_timeout(self) -> None:
        """Safety reset after 4 hours. Runs as an asyncio.Task."""
        await asyncio.sleep(4 * 3600)
        if not self._cycle_running:
            return
        self._cycle_running = False
        self._current_cycle_id = None
        self._timeout_task = None
        await self._bus.publish(BusEvent(
            type="agent.alert",
            payload={
                "agent_id": "scheduler",
                "reason": "cycle_timeout",
                "message": "Cycle timed out after 4 hours",
            },
        ))
        await self._audit.log(
            agent_id="scheduler",
            event_type="cycle_timeout",
            payload={},
            outcome="timeout",
        )
