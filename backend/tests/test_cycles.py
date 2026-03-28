import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from app.models import Base
from app.redis_bus import RedisBus
from app.services.audit import AuditService
from app.routers.cycles import router
import app.scheduler as scheduler_module

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
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def reset_scheduler():
    """Clear scheduler singleton between tests."""
    scheduler_module._scheduler = None
    yield
    scheduler_module._scheduler = None


async def test_trigger_when_scheduler_not_initialized(client):
    response = await client.post("/cycles/trigger")
    assert response.status_code == 200
    assert response.json() == {"started": False, "reason": "scheduler not initialized"}


async def test_trigger_starts_cycle(client, session_factory):
    fake_redis = fakeredis.FakeRedis()
    bus = RedisBus(redis_client=fake_redis)
    audit = AuditService(session_factory=session_factory)
    from app.scheduler import AgentScheduler, set_scheduler
    s = AgentScheduler(bus=bus, audit=audit, interval_seconds=3600)
    await s.start()
    set_scheduler(s)
    response = await client.post("/cycles/trigger")
    assert response.status_code == 200
    assert response.json() == {"started": True, "reason": None}
    await s.stop()


async def test_trigger_returns_already_running(client, session_factory):
    fake_redis = fakeredis.FakeRedis()
    bus = RedisBus(redis_client=fake_redis)
    audit = AuditService(session_factory=session_factory)
    from app.scheduler import AgentScheduler, set_scheduler
    s = AgentScheduler(bus=bus, audit=audit, interval_seconds=3600)
    await s.start()
    set_scheduler(s)
    await s.trigger()  # start a cycle
    response = await client.post("/cycles/trigger")
    assert response.status_code == 200
    assert response.json() == {"started": False, "reason": "cycle already running"}
    await s.stop()
