from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent
from app.services.llm import LLMService


class CSO(BaseAgent):
    """Chief Strategy Officer — Lead Supremacy AI prospect research.

    Listens for cycle.start, runs lead research (stub: real Google Ads
    Transparency Center scraping is a follow-on task), scores leads, and
    presents the top list to the Board for approval.

    On Board approval  → publishes leads.approved for CMO.
    On Board rejection → publishes cycle.completed {outcome: rejected}.
    """

    agent_id = "cso"

    def __init__(self, bus, audit, llm: LLMService | None = None) -> None:
        super().__init__(bus=bus, audit=audit)
        self._llm = llm
        self._current_cycle_id: str | None = None
        self._pending_leads: list = []

    async def on_start(self) -> None:
        await self.subscribe("cycle.start", self._on_cycle_start)
        await self.subscribe("decision.approved", self._on_decision_approved)
        await self.subscribe("decision.rejected", self._on_decision_rejected)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_cycle_start(self, event: BusEvent) -> None:
        if self._current_cycle_id is not None:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="cycle_start_ignored",
                payload={
                    "reason": "cycle already active",
                    "active_cycle_id": self._current_cycle_id,
                    "new_cycle_id": event.payload.get("cycle_id"),
                },
            )
            return
        self._current_cycle_id = event.payload["cycle_id"]
        await self._run_lead_research()

    async def _run_lead_research(self) -> None:
        await self._emit_status("thinking")
        try:
            leads = self._stub_leads()
            self._pending_leads = leads
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="lead_research_complete",
                payload={"lead_count": len(leads), "cycle_id": self._current_cycle_id},
                outcome="success",
            )
            description = "\n".join(
                f"• {l['name']} ({l['city']}) — Score: {l['score']}/100\n  {l['reason']}"
                for l in leads
            )
            await self.request_decision(
                title=f"Lead list ready: {len(leads)} prospects scored",
                description=description,
                extra_payload={
                    "task": "approve_leads",
                    "cycle_id": self._current_cycle_id,
                },
            )
        finally:
            await self._emit_status("active")

    def _stub_leads(self) -> list:
        """Stub lead data. Replace with real Google Ads Transparency Center scraping."""
        return [
            {
                "name": "Premier Plumbing Co",
                "city": "Atlanta, GA",
                "niche": "plumbing",
                "score": 94,
                "reason": "5+ active Google Ads, no AI voice agent detected in reviews",
            },
            {
                "name": "Elite HVAC Services",
                "city": "Dallas, TX",
                "niche": "hvac",
                "score": 91,
                "reason": "Heavy ad spend, reviews mention slow response times",
            },
            {
                "name": "QuickFix Electrical",
                "city": "Phoenix, AZ",
                "niche": "electrical",
                "score": 88,
                "reason": "Active ads, missed-call complaints in reviews",
            },
            {
                "name": "Metro Roofing LLC",
                "city": "Chicago, IL",
                "niche": "roofing",
                "score": 85,
                "reason": "Seasonal ad surge, no automation infrastructure visible",
            },
            {
                "name": "Sunrise Landscaping",
                "city": "Miami, FL",
                "niche": "landscaping",
                "score": 82,
                "reason": "Local ads running, high review volume suggests strong lead flow",
            },
        ]

    async def _on_decision_approved(self, event: BusEvent) -> None:
        event_cycle_id = event.payload.get("cycle_id")
        if event_cycle_id and event_cycle_id == self._current_cycle_id:
            leads = self._pending_leads
            cycle_id = self._current_cycle_id
            self._current_cycle_id = None
            self._pending_leads = []
            await self.publish(BusEvent(
                type="leads.approved",
                payload={"cycle_id": cycle_id, "leads": leads},
            ))
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="leads_approved",
                payload={"cycle_id": cycle_id, "lead_count": len(leads)},
                outcome="success",
            )

    async def _on_decision_rejected(self, event: BusEvent) -> None:
        event_cycle_id = event.payload.get("cycle_id")
        if event_cycle_id and event_cycle_id == self._current_cycle_id:
            cycle_id = self._current_cycle_id
            self._current_cycle_id = None
            self._pending_leads = []
            await self.publish(BusEvent(
                type="cycle.completed",
                payload={"cycle_id": cycle_id, "outcome": "rejected"},
            ))
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="leads_rejected",
                payload={"cycle_id": cycle_id},
                outcome="rejected",
            )
        else:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="decision.rejected",
                payload=event.payload,
                outcome="acknowledged",
            )
