from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent


class CSO(BaseAgent):
    """Chief Strategy Officer — market research, opportunity identification.

    Phase 2: shell only. Subscribes to decision events; logs them.
    Phase 3: will trigger market research workflows on decision.approved.
    """

    agent_id = "cso"

    async def on_start(self) -> None:
        await self.subscribe("decision.approved", self._on_decision_approved)
        await self.subscribe("decision.rejected", self._on_decision_rejected)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_decision_approved(self, event: BusEvent) -> None:
        # Phase 3: trigger market research / product direction workflow
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="decision.approved",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_decision_rejected(self, event: BusEvent) -> None:
        # Phase 3: re-evaluate strategy
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="decision.rejected",
            payload=event.payload,
            outcome="acknowledged",
        )
