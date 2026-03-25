from datetime import datetime, timezone

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

from app.models.task import Task
from app.models.decision import Decision
from app.models.audit_log import AuditLog

__all__ = ["Base", "Task", "Decision", "AuditLog", "_utcnow"]
