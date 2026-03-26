from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent
from app.services.spend_tracker import SpendTracker


class CFO(BaseAgent):
    """Chief Financial Officer — revenue tracking, cost optimization, pricing.

    Phase 3: enforces weekly soft cap. Requests Board approval if spend exceeds cap.
    """

    agent_id = "cfo"

    def __init__(self, bus, audit, spend_tracker: SpendTracker, weekly_soft_cap: float) -> None:
        super().__init__(bus=bus, audit=audit)
        self._spend_tracker = spend_tracker
        self._weekly_soft_cap = weekly_soft_cap
        self._soft_cap_requested = False  # prevent duplicate requests per week

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
        weekly_spend = event.payload.get("total_weekly_spend", 0.0)
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="revenue.updated",
            payload=event.payload,
            outcome="acknowledged",
        )
        if weekly_spend > self._weekly_soft_cap and not self._soft_cap_requested:
            self._soft_cap_requested = True
            await self.request_decision(
                title=f"Weekly spend cap exceeded: ${weekly_spend:.2f}",
                description=(
                    f"Total weekly spend ${weekly_spend:.2f} has exceeded the "
                    f"soft cap of ${self._weekly_soft_cap:.2f}. "
                    "Approve to continue spending this week."
                ),
                extra_payload={"task": "approve_overspend", "weekly_spend": weekly_spend},
            )
