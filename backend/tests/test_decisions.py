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
async def test_create_decision(client):
    resp = await client.post("/decisions", json={
        "title": "Launch in B2B invoicing",
        "description": "CSO identified high demand, low competition",
        "requested_by": "cso",
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"

@pytest.mark.asyncio
async def test_approve_decision(client):
    create = await client.post("/decisions", json={
        "title": "Spend $500 on ads",
        "description": "CMO recommends Facebook campaign",
        "requested_by": "cmo",
    })
    decision_id = create.json()["id"]
    resp = await client.post(f"/decisions/{decision_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["decided_by"] == "board"

@pytest.mark.asyncio
async def test_reject_decision(client):
    create = await client.post("/decisions", json={
        "title": "Pivot to enterprise",
        "description": "CSO wants to change target market",
        "requested_by": "cso",
    })
    decision_id = create.json()["id"]
    resp = await client.post(f"/decisions/{decision_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["decided_by"] == "board"

@pytest.mark.asyncio
async def test_cannot_approve_already_resolved_decision(client):
    create = await client.post("/decisions", json={
        "title": "Already approved",
        "description": "Should not be approvable twice",
        "requested_by": "cso",
    })
    decision_id = create.json()["id"]
    await client.post(f"/decisions/{decision_id}/approve")
    resp = await client.post(f"/decisions/{decision_id}/approve")
    assert resp.status_code == 409

@pytest.mark.asyncio
async def test_list_pending_decisions(client):
    await client.post("/decisions", json={"title": "D1", "description": "desc", "requested_by": "cso"})
    await client.post("/decisions", json={"title": "D2", "description": "desc", "requested_by": "cmo"})
    resp = await client.get("/decisions?status=pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
