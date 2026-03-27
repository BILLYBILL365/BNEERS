from __future__ import annotations

import uuid
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Enum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base, _utcnow


class DecisionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DecisionStatus] = mapped_column(Enum(DecisionStatus, values_callable=lambda x: [e.value for e in x]), default=DecisionStatus.PENDING)
    decided_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
