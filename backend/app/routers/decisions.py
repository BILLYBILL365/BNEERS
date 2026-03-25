from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.decision import Decision, DecisionStatus
from app.schemas.decision import DecisionCreate, DecisionRead

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.get("", response_model=list[DecisionRead])
async def list_decisions(status: DecisionStatus | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Decision).order_by(Decision.created_at.desc())
    if status:
        query = query.where(Decision.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=DecisionRead, status_code=201)
async def create_decision(body: DecisionCreate, db: AsyncSession = Depends(get_db)):
    decision = Decision(**body.model_dump())
    db.add(decision)
    await db.commit()
    await db.refresh(decision)
    return decision


@router.post("/{decision_id}/approve", response_model=DecisionRead)
async def approve_decision(decision_id: str, db: AsyncSession = Depends(get_db)):
    decision = await db.get(Decision, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    if decision.status != DecisionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Decision already resolved")
    decision.status = DecisionStatus.APPROVED
    decision.decided_by = "board"
    decision.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(decision)
    return decision


@router.post("/{decision_id}/reject", response_model=DecisionRead)
async def reject_decision(decision_id: str, db: AsyncSession = Depends(get_db)):
    decision = await db.get(Decision, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    if decision.status != DecisionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Decision already resolved")
    decision.status = DecisionStatus.REJECTED
    decision.decided_by = "board"
    decision.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(decision)
    return decision
