import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture(autouse=True)
def reset_agent_statuses():
    from app.routers.agents import KNOWN_AGENTS, _agent_statuses
    _agent_statuses.clear()
    _agent_statuses.update({
        agent_id: {"agent_id": agent_id, "status": "idle", "last_seen": None}
        for agent_id in KNOWN_AGENTS
    })

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_heartbeat_registers_agent(client):
    resp = await client.post("/agents/cso/heartbeat", json={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "cso"
    assert resp.json()["status"] == "active"

@pytest.mark.asyncio
async def test_get_all_agent_statuses(client):
    await client.post("/agents/cso/heartbeat", json={"status": "active"})
    await client.post("/agents/cto/heartbeat", json={"status": "thinking"})
    resp = await client.get("/agents/status")
    assert resp.status_code == 200
    agents = {a["agent_id"]: a for a in resp.json()}
    assert agents["cso"]["status"] == "active"
    assert agents["cto"]["status"] == "thinking"

@pytest.mark.asyncio
async def test_all_known_agents_returned(client):
    resp = await client.get("/agents/status")
    assert resp.status_code == 200
    statuses = {a["agent_id"]: a["status"] for a in resp.json()}
    for agent_id in ["cso", "cto", "cmo", "cfo", "coo"]:
        assert agent_id in statuses
