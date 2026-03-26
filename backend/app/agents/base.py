from __future__ import annotations

import asyncio
import uuid
from typing import Any, ClassVar

from app.redis_bus import RedisBus, EventHandler
from app.schemas.events import BusEvent
from app.services.audit import AuditService


class BaseAgent:
    agent_id: ClassVar[str]           # set by each subclass
    max_retries: ClassVar[int] = 3
    retry_backoff: list[float]        # instance attr so tests can patch it
    heartbeat_interval: ClassVar[int] = 60  # seconds

    def __init__(self, bus: RedisBus, audit: AuditService) -> None:
        self._bus = bus
        self._audit = audit
        self._running = False
        self.retry_backoff = [2.0, 4.0, 8.0]

    # ── Public lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        await self._emit_status("active")
        await self.on_start()

    async def stop(self) -> None:
        self._running = False
        await self._emit_status("idle")
        await self.on_stop()

    async def heartbeat(self) -> None:
        """Called by AgentRunner on a schedule."""
        status = "active" if self._running else "idle"
        await self._emit_status(status)

    # ── Override in subclasses ────────────────────────────────────────────

    async def on_start(self) -> None:
        """Register subscriptions here."""

    async def on_stop(self) -> None:
        """Cleanup here."""

    # ── Agent API ─────────────────────────────────────────────────────────

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        await self._bus.subscribe(event_type, handler)

    async def publish(self, event: BusEvent) -> None:
        await self._bus.publish(event)

    async def request_decision(
        self,
        title: str,
        description: str,
        extra_payload: dict | None = None,
    ) -> str:
        """Post a decision.pending event and return the decision_id."""
        decision_id = str(uuid.uuid4())
        payload = {
            "decision_id": decision_id,
            "title": title,
            "description": description,
            "requested_by": self.agent_id,
        }
        if extra_payload:
            payload.update(extra_payload)
        event = BusEvent(type="decision.pending", payload=payload)
        await self._bus.publish(event)
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="decision.pending",
            payload=event.payload,
        )
        return decision_id

    async def with_retry(self, coro_factory, context: str) -> Any:
        """Run a zero-argument async callable with retry-and-backoff.

        On success, returns the result.
        On exhausted retries, publishes an escalation event and re-raises the last exception.

        Usage:
            result = await self.with_retry(lambda: do_something(), "fetch_market_data")
        """
        last_exc: Exception | None = None
        for attempt, delay in enumerate(self.retry_backoff[: self.max_retries]):
            try:
                return await coro_factory()
            except Exception as exc:
                last_exc = exc
                await self._audit.log(
                    agent_id=self.agent_id,
                    event_type="error",
                    payload={"context": context, "attempt": attempt + 1, "error": str(exc)},
                    outcome="retrying",
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)

        # All retries exhausted
        await self._escalate(
            reason=f"All {self.max_retries} retries exhausted: {context}",
            context={"error": str(last_exc), "operation": context},
        )
        raise last_exc  # type: ignore[misc]

    # ── Internal ──────────────────────────────────────────────────────────

    async def _emit_status(self, status: str) -> None:
        event = BusEvent(
            type="agent.status",
            payload={"agent_id": self.agent_id, "status": status},
        )
        await self._bus.publish(event)

    async def _escalate(self, reason: str, context: dict[str, Any]) -> None:
        event = BusEvent(
            type="agent.escalation",
            payload={"agent_id": self.agent_id, "reason": reason, **context},
        )
        await self._bus.publish(event)
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="escalation",
            payload={"reason": reason, **context},
            outcome="escalated",
        )
