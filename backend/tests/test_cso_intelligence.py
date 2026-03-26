import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.agents.cso import CSO
from app.agents.workers.market_scanner import MarketOpportunity, MarketScanResult
from app.agents.workers.opportunity_evaluator import EvaluationResult

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
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


@pytest_asyncio.fixture
async def audit(session_factory):
    return AuditService(session_factory=session_factory)


def make_mock_llm():
    opportunity = MarketOpportunity(
        name="B2B Invoicing",
        description="Automated invoicing",
        target_market="SMB",
        estimated_arr=500_000.0,
        competition_level="medium",
        confidence_score=0.88,
    )
    scan_result = MarketScanResult(
        opportunities=[opportunity],
        reasoning="Strong SMB demand",
    )
    llm = MagicMock()
    llm.call = AsyncMock(return_value=scan_result)
    return llm


@pytest.mark.asyncio
async def test_cso_starts_market_research_on_scan_decision_approved(bus, audit):
    """When decision payload has task=market_research, CSO runs scan and requests opportunity approval."""
    llm = make_mock_llm()
    cso = CSO(bus=bus, audit=audit, llm=llm)
    await cso.start()

    # Collect decision.pending events published by the CSO handler
    captured_pending: list[BusEvent] = []
    await bus.subscribe("decision.pending", lambda e: captured_pending.append(e))

    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="decision.approved",
        payload={"decision_id": "d-1", "task": "market_research", "decided_by": "board"},
    ))

    for _ in range(20):
        await bus.process_one()

    llm.call.assert_called_once()

    found_pending = False
    for _ in range(20):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "decision.pending":
            assert event.payload["task"] == "approve_opportunity"
            assert "B2B Invoicing" in event.payload["description"]
            found_pending = True

    # Also check via subscription capture (bus semantics: events are consumed by process_one)
    if not found_pending:
        for event in captured_pending:
            if event.payload.get("task") == "approve_opportunity":
                assert "B2B Invoicing" in event.payload["description"]
                found_pending = True

    assert found_pending, "CSO should have requested Board approval for the top opportunity"


@pytest.mark.asyncio
async def test_cso_ignores_non_market_research_approvals(bus, audit):
    """Non-market-research decision approvals just get logged, no LLM called."""
    llm = make_mock_llm()
    cso = CSO(bus=bus, audit=audit, llm=llm)
    await cso.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="decision.approved",
        payload={"decision_id": "d-2", "task": "some_other_task", "decided_by": "board"},
    ))
    for _ in range(20):
        await bus.process_one()

    llm.call.assert_not_called()


@pytest.mark.asyncio
async def test_cso_publishes_task_created_on_opportunity_approved(bus, audit):
    """When Board approves an opportunity, CSO publishes task.created for CTO and CMO."""
    llm = make_mock_llm()
    cso = CSO(bus=bus, audit=audit, llm=llm)
    await cso.start()
    for _ in range(10):
        await bus.process_one()

    # Collect task.created events published by the CSO handler
    captured_tasks: list[BusEvent] = []
    await bus.subscribe("task.created", lambda e: captured_tasks.append(e))

    await bus.publish(BusEvent(
        type="decision.approved",
        payload={
            "decision_id": "d-3",
            "task": "approve_opportunity",
            "opportunity_name": "B2B Invoicing",
            "opportunity_description": "Automated invoicing for SMBs",
            "decided_by": "board",
        },
    ))
    for _ in range(30):
        await bus.process_one()

    tasks_created = []
    for _ in range(30):
        raw = await bus._redis.rpop(bus.CHANNEL)
        if raw is None:
            break
        event = BusEvent.model_validate_json(raw)
        if event.type == "task.created":
            tasks_created.append(event)

    # Also check via subscription capture (bus semantics: events may be consumed by process_one)
    tasks_created.extend(captured_tasks)

    task_types = [t.payload.get("task_type") for t in tasks_created]
    assert "build_product" in task_types
    assert "launch_campaign" in task_types
