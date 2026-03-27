from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent
from app.services.llm import LLMService


class CMO(BaseAgent):
    """Chief Marketing Officer — Lead Supremacy AI outreach.

    On leads.approved: drafts personalized cold emails for each lead (stub).
    Posts outreach drafts to the Board for approval.
    On Board approval: sends emails (stub — logs to audit), publishes cycle.completed {sent}.
    On Board rejection: publishes cycle.completed {rejected}.
    Also handles task.created for non-cycle tasks.
    """

    agent_id = "cmo"

    def __init__(self, bus, audit, llm: LLMService | None = None) -> None:
        super().__init__(bus=bus, audit=audit)
        self._llm = llm
        self._current_cycle_id: str | None = None
        self._pending_drafts: list = []

    async def on_start(self) -> None:
        await self.subscribe("leads.approved", self._on_leads_approved)
        await self.subscribe("decision.approved", self._on_decision_approved)
        await self.subscribe("decision.rejected", self._on_decision_rejected)
        await self.subscribe("task.created", self._on_task_created)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_leads_approved(self, event: BusEvent) -> None:
        if self._current_cycle_id is not None:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="leads_approved_ignored",
                payload={
                    "reason": "outreach already in progress",
                    "active_cycle_id": self._current_cycle_id,
                },
            )
            return
        self._current_cycle_id = event.payload["cycle_id"]
        leads = event.payload.get("leads", [])
        await self._draft_outreach(leads)

    async def _draft_outreach(self, leads: list) -> None:
        await self._emit_status("thinking")
        try:
            drafts = [self._stub_draft(lead) for lead in leads]
            self._pending_drafts = drafts
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="outreach_drafted",
                payload={"draft_count": len(drafts), "cycle_id": self._current_cycle_id},
                outcome="success",
            )
            preview_lines = []
            for d in drafts[:3]:
                preview_lines.append(f"To: {d['to']}\nSubject: {d['subject']}\n{d['body'][:150]}...")
            if len(drafts) > 3:
                preview_lines.append(f"...and {len(drafts) - 3} more email(s)")
            await self.request_decision(
                title=f"Outreach drafts ready: {len(drafts)} emails",
                description="\n\n---\n\n".join(preview_lines),
                extra_payload={
                    "task": "approve_outreach",
                    "cycle_id": self._current_cycle_id,
                },
            )
        finally:
            await self._emit_status("active")

    def _stub_draft(self, lead: dict) -> dict:
        """Stub email draft. Replace with LLM-generated personalized copy."""
        name = lead.get("name", "Business Owner")
        city = lead.get("city", "")
        niche = lead.get("niche", "service")
        slug = name.lower().replace(" ", "").replace(",", "")
        return {
            "to": f"owner@{slug}.com",
            "subject": f"Question about your {niche} business in {city}",
            "body": (
                f"Hi {name},\n\n"
                f"I noticed you're running Google Ads for your {niche} business in {city}. "
                f"We help local {niche} companies capture missed calls 24/7 with AI voice agents "
                f"— most clients recover $8,000–$15,000/month in lost revenue within 30 days.\n\n"
                f"Would you be open to a quick 10-minute call to see if it's a fit?\n\n"
                f"Best,\nLead Supremacy AI Team"
            ),
        }

    async def _on_decision_approved(self, event: BusEvent) -> None:
        event_cycle_id = event.payload.get("cycle_id")
        if event_cycle_id and event_cycle_id == self._current_cycle_id:
            drafts = self._pending_drafts
            cycle_id = self._current_cycle_id
            self._current_cycle_id = None
            self._pending_drafts = []
            await self._send_outreach(drafts, cycle_id)
        else:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="decision.approved",
                payload=event.payload,
                outcome="acknowledged",
            )

    async def _send_outreach(self, drafts: list, cycle_id: str) -> None:
        """Send outreach emails. Stubbed — logs to audit. Replace with SMTP/API integration."""
        for draft in drafts:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="email_sent",
                payload={"to": draft["to"], "subject": draft["subject"], "cycle_id": cycle_id},
                outcome="sent",
            )
        await self.publish(BusEvent(
            type="cycle.completed",
            payload={"cycle_id": cycle_id, "outcome": "sent"},
        ))
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="outreach_complete",
            payload={"email_count": len(drafts), "cycle_id": cycle_id},
            outcome="success",
        )

    async def _on_decision_rejected(self, event: BusEvent) -> None:
        event_cycle_id = event.payload.get("cycle_id")
        if event_cycle_id and event_cycle_id == self._current_cycle_id:
            cycle_id = self._current_cycle_id
            self._current_cycle_id = None
            self._pending_drafts = []
            await self.publish(BusEvent(
                type="cycle.completed",
                payload={"cycle_id": cycle_id, "outcome": "rejected"},
            ))
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="outreach_rejected",
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

    async def _on_task_created(self, event: BusEvent) -> None:
        if event.payload.get("assignee") != self.agent_id:
            return
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="task.created",
            payload=event.payload,
            outcome="acknowledged",
        )
