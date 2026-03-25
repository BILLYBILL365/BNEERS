import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.main import app
from app.database import get_db

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async def override_get_db():
        async with session_factory() as session:
            yield session
    app.dependency_overrides[get_db] = override_get_db
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_create_task(client):
    resp = await client.post("/tasks", json={"title": "Research market", "agent_id": "cso"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Research market"
    assert data["agent_id"] == "cso"
    assert data["status"] == "pending"

@pytest.mark.asyncio
async def test_list_tasks(client):
    await client.post("/tasks", json={"title": "Task 1", "agent_id": "cso"})
    await client.post("/tasks", json={"title": "Task 2", "agent_id": "cto"})
    resp = await client.get("/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

@pytest.mark.asyncio
async def test_update_task_status(client):
    create = await client.post("/tasks", json={"title": "Build feature", "agent_id": "cto"})
    task_id = create.json()["id"]
    resp = await client.patch(f"/tasks/{task_id}", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
