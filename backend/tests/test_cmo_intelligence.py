import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.agents.cmo import CMO
from app.agents.workers.content_writer import ContentPackage
from app.agents.workers.ad_manager import AdCopy
from app.agents.workers.social_media import SocialPosts

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


def make_cmo(bus, audit):
    llm = MagicMock()
    llm.call = AsyncMock(side_effect=[
        ContentPackage(
            landing_page_headline="Invoice faster",
            landing_page_body="Copy here.",
            blog_post_titles=["5 tips"],
            email_subject="Stop chasing payments",
        ),
        AdCopy(headline="Invoice faster", body="Never chase payments", cta="Try free", estimated_cpc=2.50),
        SocialPosts(twitter=["Launch tweet!"], linkedin=["Launch post"]),
    ])
    return CMO(bus=bus, audit=audit, llm=llm)


@pytest.mark.asyncio
async def test_cmo_runs_campaign_on_launch_campaign_task(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    cmo = make_cmo(bus, audit)
    await cmo.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="task.created",
        payload={
            "task_type": "launch_campaign",
            "assignee": "cmo",
            "product_name": "B2B Invoicing",
            "product_description": "Automated invoicing",
        },
    ))
    for _ in range(30):
        await bus.process_one()

    assert cmo._llm.call.call_count == 3


@pytest.mark.asyncio
async def test_cmo_publishes_task_completed(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    cmo = make_cmo(bus, audit)
    await cmo.start()
    for _ in range(10):
        await bus.process_one()

    completed = []
    await bus.subscribe("task.completed", lambda e: completed.append(e))

    await bus.publish(BusEvent(
        type="task.created",
        payload={
            "task_type": "launch_campaign",
            "assignee": "cmo",
            "product_name": "B2B Invoicing",
            "product_description": "Automated invoicing",
        },
    ))
    for _ in range(30):
        await bus.process_one()

    assert any(e.payload.get("task_type") == "launch_campaign" for e in completed)
