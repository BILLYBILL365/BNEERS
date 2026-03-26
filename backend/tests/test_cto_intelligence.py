import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.audit import AuditService
from app.agents.cto import CTO
from app.agents.workers.code_writer import CodeScaffold
from app.agents.workers.qa_tester import TestPlan
from app.agents.workers.devops import DeploymentConfig

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


def make_cto(bus, audit):
    llm = MagicMock()
    llm.call = AsyncMock(side_effect=[
        CodeScaffold(
            project_structure=["src/main.py"],
            main_code="# entry",
            dependencies=["fastapi"],
            setup_instructions="pip install",
        ),
        TestPlan(test_cases=["test_create"], testing_framework="pytest", coverage_target=80),
        DeploymentConfig(
            dockerfile="FROM python:3.12",
            railway_config={},
            environment_variables=["DATABASE_URL"],
            deploy_steps=["build", "start"],
        ),
    ])
    return CTO(bus=bus, audit=audit, llm=llm)


@pytest.mark.asyncio
async def test_cto_runs_pipeline_on_build_product_task(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    cto = make_cto(bus, audit)
    await cto.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="task.created",
        payload={
            "task_type": "build_product",
            "assignee": "cto",
            "product_name": "B2B Invoicing",
            "product_description": "Automated invoicing",
        },
    ))
    for _ in range(30):
        await bus.process_one()

    assert cto._llm.call.call_count == 3


@pytest.mark.asyncio
async def test_cto_publishes_task_completed_after_pipeline(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    cto = make_cto(bus, audit)
    await cto.start()
    for _ in range(10):
        await bus.process_one()

    completed_events = []
    await bus.subscribe("task.completed", lambda e: completed_events.append(e))

    await bus.publish(BusEvent(
        type="task.created",
        payload={
            "task_type": "build_product",
            "assignee": "cto",
            "product_name": "B2B Invoicing",
            "product_description": "Automated invoicing",
        },
    ))
    for _ in range(30):
        await bus.process_one()

    assert any(e.payload.get("task_type") == "build_product" for e in completed_events)


@pytest.mark.asyncio
async def test_cto_ignores_tasks_not_assigned_to_it(bus, session_factory):
    audit = AuditService(session_factory=session_factory)
    cto = make_cto(bus, audit)
    await cto.start()
    for _ in range(10):
        await bus.process_one()

    await bus.publish(BusEvent(
        type="task.created",
        payload={"task_type": "launch_campaign", "assignee": "cmo"},
    ))
    for _ in range(20):
        await bus.process_one()

    cto._llm.call.assert_not_called()
