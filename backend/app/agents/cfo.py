from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent


class CFO(BaseAgent):
    """Chief Financial Officer — revenue tracking, cost optimization, pricing.

    Phase 2: shell only. Subscribes to task.completed to track work throughput.
    Phase 3: will update Revenue Tracker and Pricing Optimizer workers.
    """

    agent_id = "cfo"

    async def on_start(self) -> None:
        await self.subscribe("task.completed", self._on_task_completed)
        await self.subscribe("revenue.updated", self._on_revenue_updated)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_task_completed(self, event: BusEvent) -> None:
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="task.completed",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_revenue_updated(self, event: BusEvent) -> None:
        # Phase 3: check weekly soft cap, trigger Board alert if needed
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="revenue.updated",
            payload=event.payload,
            outcome="acknowledged",
        )
