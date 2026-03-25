import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.models.audit_log import AuditLog
from app.services.audit import AuditService

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session

@pytest_asyncio.fixture
async def audit(session_factory):
    return AuditService(session_factory=session_factory)

@pytest.mark.asyncio
async def test_log_writes_record(audit, db_session):
    await audit.log(
        agent_id="cso",
        event_type="decision.pending",
        payload={"market": "B2B invoicing"},
    )
    from sqlalchemy import select
    result = await db_session.execute(select(AuditLog))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].agent_id == "cso"
    assert rows[0].event_type == "decision.pending"
    assert rows[0].payload == {"market": "B2B invoicing"}
    assert rows[0].outcome is None

@pytest.mark.asyncio
async def test_log_with_outcome(audit, db_session):
    await audit.log(
        agent_id="cto",
        event_type="error",
        payload={"error": "timeout"},
        outcome="retrying",
    )
    from sqlalchemy import select
    result = await db_session.execute(select(AuditLog))
    rows = result.scalars().all()
    assert rows[0].outcome == "retrying"

@pytest.mark.asyncio
async def test_log_with_decision_by(audit, db_session):
    await audit.log(
        agent_id="cso",
        event_type="decision",
        payload={"decision_id": "abc"},
        decision_by="board",
        outcome="approved",
    )
    from sqlalchemy import select
    result = await db_session.execute(select(AuditLog))
    rows = result.scalars().all()
    assert rows[0].decision_by == "board"
    assert rows[0].outcome == "approved"
