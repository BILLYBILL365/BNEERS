from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel
from app.models.decision import DecisionStatus


class DecisionCreate(BaseModel):
    title: str
    description: str
    requested_by: str


class DecisionRead(BaseModel):
    id: str
    title: str
    description: str
    requested_by: str
    status: DecisionStatus
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime
    cycle_id: str | None = None
    model_config = {"from_attributes": True}
