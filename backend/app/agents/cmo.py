from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent
from app.services.llm import LLMService
from app.agents.workers.content_writer import ContentWriter
from app.agents.workers.ad_manager import AdManager
from app.agents.workers.social_media import SocialMedia


class CMO(BaseAgent):
    """Chief Marketing Officer — content, ads, SEO, social, email.

    Phase 3: on task.created(task_type=launch_campaign, assignee=cmo), runs
    Content → Ads → Social pipeline.
    """

    agent_id = "cmo"

    def __init__(self, bus, audit, llm: LLMService | None = None) -> None:
        super().__init__(bus=bus, audit=audit)
        self._llm = llm
        self._content_writer = ContentWriter(llm=llm) if llm else None
        self._ad_manager = AdManager(llm=llm) if llm else None
        self._social_media = SocialMedia(llm=llm) if llm else None

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
        if task_type == "launch_campaign" and self._content_writer:
            await self._run_campaign_pipeline(event)
        else:
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="task.created",
                payload=event.payload,
                outcome="acknowledged",
            )

    async def _run_campaign_pipeline(self, event: BusEvent) -> None:
        name = event.payload.get("product_name", "Unknown")
        await self._emit_status("thinking")
        try:
            content = await self.with_retry(
                lambda: self._content_writer.create(name, target_market="SMB"),
                context="content_creation",
            )
            ad_copy = await self.with_retry(
                lambda: self._ad_manager.create_ad(name, budget=50.0),
                context="ad_creation",
            )
            social = await self.with_retry(
                lambda: self._social_media.create_posts(name),
                context="social_posts",
            )
            await self._audit.log(
                agent_id=self.agent_id,
                event_type="campaign_pipeline_complete",
                payload={
                    "product_name": name,
                    "headline": content.landing_page_headline,
                    "email_subject": content.email_subject,
                    "ad_cta": ad_copy.cta,
                    "tweets": social.twitter,
                },
                outcome="success",
            )
            await self.publish(BusEvent(
                type="task.completed",
                payload={
                    "task_type": "launch_campaign",
                    "product_name": name,
                    "completed_by": self.agent_id,
                },
            ))
        finally:
            await self._emit_status("active")
