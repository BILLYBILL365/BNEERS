from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.services.llm import LLMService
from app.services.spend_tracker import SpendTracker
from app.agents.cso import CSO
from app.agents.cto import CTO
from app.agents.cmo import CMO
from app.agents.cfo import CFO
from app.agents.coo import COO


class AgentRunner:
    """Starts and coordinates all C-Suite agents."""

    def __init__(
        self,
        bus: RedisBus,
        audit: AuditService,
        anthropic_api_key: str = "",
        weekly_soft_cap: float = 500.0,
        daily_cap_ads: float = 100.0,
        daily_cap_apis: float = 50.0,
    ) -> None:
        self._bus = bus
        self._audit = audit
        self.agents: dict[str, Any] = {}
        self.status_store: dict[str, Any] = {}

        llm_smart: LLMService | None = None
        llm_fast: LLMService | None = None
        if anthropic_api_key:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=anthropic_api_key)
            llm_smart = LLMService(client=client, model="claude-sonnet-4-6")
            llm_fast = LLMService(client=client, model="claude-haiku-4-5-20251001")

        spend_tracker = SpendTracker(
            bus=bus, daily_cap_ads=daily_cap_ads, daily_cap_apis=daily_cap_apis
        )

        self.agents = {
            "cso": CSO(bus=bus, audit=audit, llm=llm_smart),
            "cto": CTO(bus=bus, audit=audit, llm=llm_smart),
            "cmo": CMO(bus=bus, audit=audit, llm=llm_fast),
            "cfo": CFO(
                bus=bus, audit=audit,
                spend_tracker=spend_tracker,
                weekly_soft_cap=weekly_soft_cap,
            ),
            "coo": COO(bus=bus, audit=audit),
        }

    async def start(self) -> None:
        await self._bus.subscribe("agent.status", self._on_agent_status)
        for agent in self.agents.values():
            await agent.start()

    async def stop(self) -> None:
        for agent in self.agents.values():
            await agent.stop()

    async def heartbeat_all(self) -> None:
        for agent in self.agents.values():
            await agent.heartbeat()

    async def _on_agent_status(self, event: BusEvent) -> None:
        agent_id = event.payload.get("agent_id")
        status = event.payload.get("status")
        if agent_id and status:
            self.status_store[agent_id] = {
                "agent_id": agent_id,
                "status": status,
                "last_seen": datetime.now(timezone.utc),
            }
