"""
Staging smoke tests — run these against a live Docker Compose stack.

Pre-requisite:
    docker compose up -d   (from project root)

Skip automatically if the backend is not reachable (CI without Docker).
"""
import pytest
import httpx

BASE_URL = "http://localhost:8000"


def _backend_is_up() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _backend_is_up(),
    reason="Docker Compose stack not running — skipping staging smoke tests",
)


def test_health_endpoint():
    r = httpx.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_agents_status_has_all_csuite():
    r = httpx.get(f"{BASE_URL}/agents/status")
    assert r.status_code == 200
    agent_ids = {a["agent_id"] for a in r.json()}
    for expected in ("cso", "cto", "cmo", "cfo", "coo"):
        assert expected in agent_ids, f"Agent '{expected}' not in status list"


def test_decisions_endpoint_responds():
    r = httpx.get(f"{BASE_URL}/decisions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_tasks_endpoint_responds():
    r = httpx.get(f"{BASE_URL}/tasks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_and_retrieve_decision():
    """Create a decision via POST and retrieve it via GET."""
    payload = {
        "title": "Staging test decision",
        "description": "Auto-created by staging smoke test",
        "requested_by": "smoke_test",
    }
    r = httpx.post(f"{BASE_URL}/decisions", json=payload)
    assert r.status_code == 201
    decision = r.json()
    assert decision["status"] == "pending"
    decision_id = decision["id"]

    # Retrieve it
    r2 = httpx.get(f"{BASE_URL}/decisions")
    assert r2.status_code == 200
    ids = [d["id"] for d in r2.json()]
    assert decision_id in ids
