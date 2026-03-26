from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent
from app.services.llm import LLMService
from app.agents.workers.code_writer import CodeWriter
from app.agents.workers.qa_tester import QATester
from app.agents.workers.devops import DevOps


class CTO(BaseAgent):
    """Chief Technology Officer — builds and ships the SaaS.

    Phase 3: on task.created(task_type=build_product, assignee=cto), runs
    Code Writer → QA → DevOps pipeline.
    """

    agent_id = "cto"

    def __init__(self, bus, audit, llm: LLMService | None = None) -> None:
        super().__init__(bus=bus, audit=audit)
        self._llm = llm
        self._code_writer = CodeWriter(llm=llm) if llm else None
        self._qa_tester = QATester(llm=llm) if llm else None
        self._devops = DevOps(llm=llm) if llm else None

    async def on_start(self) -> None:
        await self.subscribe("decision.approved", self._on_decision_approved)
        await self.subscribe("task.created", self._on_task_created)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_decision_approved(self, event: BusEvent) -> None:
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="decision.approved",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_task_created(self, event: BusEvent) -> None:
        if event.payload.get("assignee") != self.agent_id:
            return
        task_type = event.payload.get("task_type")
        if task_type == "build_product" and self._code_writer:
            await self._run_build_pipeline(event)
        else:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="task.created",
                payload=event.payload,
                outcome="acknowledged",
            )

    async def _run_build_pipeline(self, event: BusEvent) -> None:
        name = event.payload.get("product_name", "Unknown")
        description = event.payload.get("product_description", "")
        await self._emit_status("thinking")
        try:
            scaffold = await self.with_retry(
                lambda: self._code_writer.write(name, description),
                context="code_generation",
            )
            test_plan = await self.with_retry(
                lambda: self._qa_tester.create_plan(name, scaffold.project_structure),
                context="qa_test_plan",
            )
            deploy_config = await self.with_retry(
                lambda: self._devops.create_config(name),
                context="deployment_config",
            )
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="build_pipeline_complete",
                payload={
                    "product_name": name,
                    "files": scaffold.project_structure,
                    "test_cases": test_plan.test_cases,
                    "deploy_steps": deploy_config.deploy_steps,
                },
                outcome="success",
            )
            await self.publish(BusEvent(
                type="task.completed",
                payload={
                    "task_type": "build_product",
                    "product_name": name,
                    "completed_by": self.agent_id,
                    "scaffold_files": scaffold.project_structure,
                },
            ))
        finally:
            await self._emit_status("active")
