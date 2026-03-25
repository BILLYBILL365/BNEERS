from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.decision import Decision, DecisionStatus
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService


class DecisionService:
    """Bridges decision.pending/approved/rejected bus events with the decisions DB table."""

    def __init__(self, bus: RedisBus, session_factory: async_sessionmaker[AsyncSession], audit: AuditService) -> None:
        self._bus = bus
        self._session_factory = session_factory
        self._audit = audit

    async def start(self) -> None:
        """Register bus subscriptions. Call once at startup."""
        await self._bus.subscribe("decision.pending", self._on_pending)
        await self._bus.subscribe("decision.approved", self._on_resolved)
        await self._bus.subscribe("decision.rejected", self._on_resolved)

    async def _on_pending(self, event: BusEvent) -> None:
        payload = event.payload
        decision_id: str = payload.get("decision_id", "")

        async with self._session_factory() as session:
            # Idempotent — skip if already in DB
            existing = await session.get(Decision, decision_id)
            if existing is not None:
                return

            decision = Decision(
                id=decision_id,
                title=payload.get("title", ""),
                description=payload.get("description", ""),
                requested_by=payload.get("requested_by", "unknown"),
                status=DecisionStatus.PENDING,
            )
            session.add(decision)
            await session.commit()

        await self._audit.log(
            agent_id=payload.get("requested_by", "unknown"),
            event_type="decision.pending",
            payload=payload,
        )

    async def _on_resolved(self, event: BusEvent) -> None:
        payload = event.payload
        await self._audit.log(
            agent_id=payload.get("decided_by", "board"),
            event_type=event.type,
            payload=payload,
            decision_by=payload.get("decided_by", "board"),
            outcome=event.type.split(".")[-1],  # "approved" or "rejected"
        )
