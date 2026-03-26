"""
Phase 3 integration test: CSO market research → Board approval → CTO + CMO pipelines run →
CFO tracks revenue → COO coordinates. All LLM calls mocked.
"""
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.models.audit_log import AuditLog
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.services.spend_tracker import SpendTracker
from app.agents.cso import CSO
from app.agents.cto import CTO
from app.agents.cmo import CMO
from app.agents.cfo import CFO
from app.agents.coo import COO
from app.agents.workers.market_scanner import MarketOpportunity, MarketScanResult
from app.agents.workers.code_writer import CodeScaffold
from app.agents.workers.qa_tester import QATestPlan
from app.agents.workers.devops import DeploymentConfig
from app.agents.workers.content_writer import ContentPackage
from app.agents.workers.ad_manager import AdCopy
from app.agents.workers.social_media import SocialPosts

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    e = create_async_engine(TEST_DB)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await e.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def bus():
    return RedisBus(redis_client=fakeredis.FakeRedis())


def make_cso_llm():
    opportunity = MarketOpportunity(
        name="B2B Invoicing",
        description="Automated invoicing",
        target_market="SMB",
        estimated_arr=500_000.0,
        competition_level="medium",
        confidence_score=0.88,
    )
    llm = MagicMock()
    llm.call = AsyncMock(return_value=MarketScanResult(
        opportunities=[opportunity], reasoning="Strong demand"
    ))
    return llm


def make_cto_llm():
    llm = MagicMock()
    llm.call = AsyncMock(side_effect=[
        CodeScaffold(project_structure=["src/main.py"], main_code="# entry",
                     dependencies=["fastapi"], setup_instructions="pip install"),
        QATestPlan(test_cases=["test_invoice"], testing_framework="pytest", coverage_target=80),
        DeploymentConfig(dockerfile="FROM python:3.12", railway_config={},
                         environment_variables=["DATABASE_URL"], deploy_steps=["build", "start"]),
    ])
    return llm


def make_cmo_llm():
    llm = MagicMock()
    llm.call = AsyncMock(side_effect=[
        ContentPackage(landing_page_headline="Invoice faster", landing_page_body="copy",
                       blog_post_titles=["5 tips"], email_subject="Stop chasing"),
        AdCopy(headline="Invoice faster", body="Never chase payments",
               cta="Try free", estimated_cpc=2.50),
        SocialPosts(twitter=["Launch!"], linkedin=["We launched"]),
    ])
    return llm


@pytest.mark.asyncio
async def test_full_phase3_pipeline(bus, session_factory, db_session):
    """Full pipeline: market_research approved → CSO scans → opportunity approved →
    CTO builds product + CMO launches campaign → CFO tracks revenue."""
    audit = AuditService(session_factory=session_factory)
    spend_tracker = SpendTracker(bus=bus, daily_cap_ads=1000.0, daily_cap_apis=500.0)

    cso_llm = make_cso_llm()
    cto_llm = make_cto_llm()
    cmo_llm = make_cmo_llm()

    cso = CSO(bus=bus, audit=audit, llm=cso_llm)
    cto = CTO(bus=bus, audit=audit, llm=cto_llm)
    cmo = CMO(bus=bus, audit=audit, llm=cmo_llm)
    cfo = CFO(bus=bus, audit=audit, spend_tracker=spend_tracker, weekly_soft_cap=500.0)
    coo = COO(bus=bus, audit=audit)

    for agent in [cso, cto, cmo, cfo, coo]:
        await agent.start()

    # Drain startup events
    for _ in range(50):
        await bus.process_one()

    # Step 1: Board approves "run market research"
    await bus.publish(BusEvent(
        type="decision.approved",
        payload={"decision_id": "d-market", "task": "market_research", "decided_by": "board"},
    ))
    for _ in range(50):
        await bus.process_one()

    # CSO should have called LLM once for market scan
    cso_llm.call.assert_called_once()

    # Step 2: Board approves the opportunity
    await bus.publish(BusEvent(
        type="decision.approved",
        payload={
            "decision_id": "d-opp",
            "task": "approve_opportunity",
            "opportunity_name": "B2B Invoicing",
            "opportunity_description": "Automated invoicing for SMBs",
            "decided_by": "board",
        },
    ))
    for _ in range(100):
        await bus.process_one()

    # CTO should have run 3-step pipeline
    assert cto_llm.call.call_count == 3
    # CMO should have run 3-step pipeline
    assert cmo_llm.call.call_count == 3

    # Step 3: Revenue update (under cap — no decision request)
    await bus.publish(BusEvent(
        type="revenue.updated",
        payload={"weekly_revenue": 10_000.0, "total_weekly_spend": 200.0},
    ))
    for _ in range(30):
        await bus.process_one()

    # Verify audit log has complete trail
    result = await db_session.execute(
        select(AuditLog).order_by(AuditLog.timestamp)
    )
    logs = result.scalars().all()
    event_types = {log.event_type for log in logs}

    assert "agent_started" in event_types
    assert "market_research_complete" in event_types
    assert "build_pipeline_complete" in event_types
    assert "campaign_pipeline_complete" in event_types
    assert "revenue.updated" in event_types


@pytest.mark.asyncio
async def test_coo_tracks_tasks_from_full_pipeline(bus, session_factory):
    """COO sees task.created events with dependencies and builds graph."""
    audit = AuditService(session_factory=session_factory)
    coo = COO(bus=bus, audit=audit)
    await coo.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_id": "build-1", "depends_on": [], "task_type": "build_product"},
    ))
    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_id": "deploy-1", "depends_on": ["build-1"], "task_type": "deploy"},
    ))
    for _ in range(20):
        await bus.process_one()

    assert "build-1" in coo._task_graph
    assert "deploy-1" in coo._task_graph
    assert "build-1" in coo._task_graph["deploy-1"]["depends_on"]
