from datetime import datetime
from typing import Literal
try:
    from datetime import UTC
except ImportError:
    # Python 3.10 compatibility
    from datetime import timezone
    UTC = timezone.utc

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/agents", tags=["agents"])

KNOWN_AGENTS = [
    "cso", "cto", "cmo", "cfo", "coo",
    "market_scanner", "opportunity_evaluator",
    "code_writer", "qa_tester", "devops",
    "content_writer", "social_media", "email_campaign", "ad_manager",
    "revenue_tracker", "pricing_optimizer",
    "support_agent", "task_coordinator",
]

# In-process status store — written by AgentRunner (agent.status bus events) and the heartbeat endpoint
_agent_statuses: dict[str, dict] = {
    agent_id: {"agent_id": agent_id, "status": "idle", "last_seen": None}
    for agent_id in KNOWN_AGENTS
}

class HeartbeatRequest(BaseModel):
    status: Literal["active", "thinking", "idle"]

class AgentStatus(BaseModel):
    agent_id: str
    status: str
    last_seen: datetime | None

@router.post("/{agent_id}/heartbeat", response_model=AgentStatus)
async def heartbeat(agent_id: str, body: HeartbeatRequest):
    _agent_statuses[agent_id] = {
        "agent_id": agent_id,
        "status": body.status,
        "last_seen": datetime.now(UTC),
    }
    return _agent_statuses[agent_id]

@router.get("/status", response_model=list[AgentStatus])
async def get_all_statuses():
    return list(_agent_statuses.values())
