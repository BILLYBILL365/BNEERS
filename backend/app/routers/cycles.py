from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from app.scheduler import get_scheduler

router = APIRouter(prefix="/cycles", tags=["cycles"])


class CycleTriggerResponse(BaseModel):
    started: bool
    reason: str | None = None


@router.post("/trigger", response_model=CycleTriggerResponse)
async def trigger_cycle() -> CycleTriggerResponse:
    """Manually trigger a new business cycle. Returns immediately."""
    scheduler = get_scheduler()
    if scheduler is None:
        return CycleTriggerResponse(started=False, reason="scheduler not initialized")
    started = await scheduler.trigger()
    if started:
        return CycleTriggerResponse(started=True)
    return CycleTriggerResponse(started=False, reason="cycle already running")
