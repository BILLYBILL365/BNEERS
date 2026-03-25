from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent


class COO(BaseAgent):
    """Chief Operating Officer — customer support, task coordination, dependency resolution.

    Phase 2: shell only. Tracks all task lifecycle events.
    Phase 3: will handle deadlock detection and resolution.
    """

    agent_id = "coo"

    async def on_start(self) -> None:
        await self.subscribe("task.created", self._on_task_created)
        await self.subscribe("task.completed", self._on_task_completed)
        await self.subscribe("agent.escalation", self._on_escalation)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_task_created(self, event: BusEvent) -> None:
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="task.created",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_task_completed(self, event: BusEvent) -> None:
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="task.completed",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_escalation(self, event: BusEvent) -> None:
        # Phase 3: attempt auto-resolution; otherwise surface to Board
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="escalation_received",
            payload=event.payload,
            outcome="acknowledged",
        )
