from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent
from app.services.llm import LLMService
from app.agents.workers.market_scanner import MarketScanner
from app.agents.workers.opportunity_evaluator import OpportunityEvaluator


class CSO(BaseAgent):
    """Chief Strategy Officer — market research, opportunity identification.

    Phase 3: triggers real market research on decision.approved(task=market_research).
    When Board approves top opportunity, publishes task.created for CTO + CMO.
    """

    agent_id = "cso"

    def __init__(self, bus, audit, llm: LLMService | None = None) -> None:
        super().__init__(bus=bus, audit=audit)
        self._scanner = MarketScanner(llm=llm) if llm else None
        self._evaluator = OpportunityEvaluator()

    async def on_start(self) -> None:
        await self.subscribe("decision.approved", self._on_decision_approved)
        await self.subscribe("decision.rejected", self._on_decision_rejected)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_decision_approved(self, event: BusEvent) -> None:
        task = event.payload.get("task")
        if task == "market_research":
            await self._run_market_research()
        elif task == "approve_opportunity":
            await self._on_opportunity_approved(event)
        else:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="decision.approved",
                payload=event.payload,
                outcome="acknowledged",
            )

    async def _run_market_research(self) -> None:
        if self._scanner is None:
            return
        await self._emit_status("thinking")
        scan_result = await self.with_retry(
            lambda: self._scanner.scan(),
            context="market_scan",
        )
        evaluation = await self._evaluator.evaluate(scan_result.opportunities)
        top = evaluation.top_opportunity
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="market_research_complete",
            payload={"top_opportunity": top.name, "rationale": evaluation.rationale},
            outcome="success",
        )
        await self.request_decision(
            title=f"Pursue opportunity: {top.name}",
            description=(
                f"{evaluation.rationale}\n\n"
                f"ARR estimate: ${top.estimated_arr:,.0f}. "
                f"Target market: {top.target_market}."
            ),
            extra_payload={
                "task": "approve_opportunity",
                "opportunity_name": top.name,
                "opportunity_description": top.description,
            },
        )
        await self._emit_status("active")

    async def _on_opportunity_approved(self, event: BusEvent) -> None:
        name = event.payload.get("opportunity_name", "Unknown")
        description = event.payload.get("opportunity_description", "")
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="opportunity_approved",
            payload=event.payload,
            outcome="success",
        )
        for task_type, assignee in [("build_product", "cto"), ("launch_campaign", "cmo")]:
            await self.publish(BusEvent(
                type="task.created",
                payload={
                    "task_type": task_type,
                    "assignee": assignee,
                    "product_name": name,
                    "product_description": description,
                    "requested_by": self.agent_id,
                },
            ))

    async def _on_decision_rejected(self, event: BusEvent) -> None:
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="decision.rejected",
            payload=event.payload,
            outcome="acknowledged",
        )
