import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.models.task import Task, TaskStatus
from app.models.decision import Decision, DecisionStatus
from app.models.audit_log import AuditLog

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_create_task(db_session):
    task = Task(title="Build MVP", agent_id="cto", status=TaskStatus.PENDING)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    assert task.id is not None
    assert task.status == TaskStatus.PENDING

@pytest.mark.asyncio
async def test_create_decision(db_session):
    decision = Decision(
        title="Launch SaaS product",
        description="CSO recommends targeting B2B invoicing market",
        requested_by="cso",
        status=DecisionStatus.PENDING,
    )
    db_session.add(decision)
    await db_session.commit()
    await db_session.refresh(decision)
    assert decision.id is not None
    assert decision.status == DecisionStatus.PENDING

@pytest.mark.asyncio
async def test_create_audit_log(db_session):
    log = AuditLog(
        agent_id="cso",
        event_type="decision",
        payload={"market": "B2B invoicing", "confidence": 0.87},
        decision_by="cso",
        outcome="success",
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    assert log.id is not None
    assert log.payload["market"] == "B2B invoicing"
