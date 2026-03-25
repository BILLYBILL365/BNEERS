from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.agents.cso import CSO
from app.agents.cto import CTO
from app.agents.cmo import CMO
from app.agents.cfo import CFO
from app.agents.coo import COO
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService

CSUITE_CLASSES = [CSO, CTO, CMO, CFO, COO]


class AgentRunner:
    """Manages the lifecycle of all C-Suite agents and the bus event loop.

    Usage (in FastAPI lifespan):
        runner = AgentRunner(bus=bus, audit=audit)
        runner.status_store = _agent_statuses  # from routers/agents.py
        await runner.start()
        asyncio.create_task(bus.run_forever())
        ...
        await runner.stop()
    """

    def __init__(self, bus: RedisBus, audit: AuditService) -> None:
        self._bus = bus
        self._audit = audit
        self.agents: dict[str, BaseAgent] = {}
        self.status_store: dict = {}  # injected by main.py — points to _agent_statuses

    async def start(self) -> None:
        # Subscribe to agent.status events to keep status_store current
        await self._bus.subscribe("agent.status", self._on_agent_status)

        # Instantiate and start all C-Suite agents
        for AgentClass in CSUITE_CLASSES:
            agent = AgentClass(bus=self._bus, audit=self._audit)
            self.agents[agent.agent_id] = agent
            await agent.start()

    async def stop(self) -> None:
        for agent in self.agents.values():
            await agent.stop()

    async def heartbeat_all(self) -> None:
        """Call each agent's heartbeat method. Run on a schedule."""
        for agent in self.agents.values():
            await agent.heartbeat()

    async def _on_agent_status(self, event: BusEvent) -> None:
        agent_id: str = event.payload.get("agent_id", "")
        status: str = event.payload.get("status", "idle")
        if agent_id:
            self.status_store[agent_id] = {
                "agent_id": agent_id,
                "status": status,
                "last_seen": datetime.now(timezone.utc),
            }
