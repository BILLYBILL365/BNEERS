from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent


class CTO(BaseAgent):
    """Chief Technology Officer — builds and ships the SaaS.

    Phase 2: shell only. Subscribes to task and decision events.
    Phase 3: will spawn Code Writer, QA, DevOps worker agents.
    """

    agent_id = "cto"

    async def on_start(self) -> None:
        await self.subscribe("decision.approved", self._on_decision_approved)
        await self.subscribe("task.created", self._on_task_created)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_decision_approved(self, event: BusEvent) -> None:
        # Phase 3: spin up Code Writer → QA → DevOps pipeline
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="decision.approved",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_task_created(self, event: BusEvent) -> None:
        # Phase 3: delegate to worker agents
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="task.created",
            payload=event.payload,
            outcome="acknowledged",
        )
