from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def log(
        self,
        *,
        agent_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        decision_by: str | None = None,
        outcome: str | None = None,
    ) -> AuditLog:
        record = AuditLog(
            agent_id=agent_id,
            event_type=event_type,
            payload=payload or {},
            decision_by=decision_by,
            outcome=outcome,
        )
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record
