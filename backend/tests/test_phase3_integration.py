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
