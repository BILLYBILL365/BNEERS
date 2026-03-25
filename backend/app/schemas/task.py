from __future__ import annotations

from pydantic import BaseModel
from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    title: str
    agent_id: str
    parent_agent_id: str | None = None


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    title: str | None = None


class TaskRead(BaseModel):
    id: str
    title: str
    agent_id: str
    parent_agent_id: str | None
    status: TaskStatus
    model_config = {"from_attributes": True}
