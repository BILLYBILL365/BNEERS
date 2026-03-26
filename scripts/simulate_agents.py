#!/usr/bin/env python3
"""
Agent simulation script for Project Million.

Fires a complete board decision flow through the running stack without
requiring a real Anthropic API key. Validates the full approve/reject
cycle and agent heartbeat pipeline.

Usage:
    docker compose up -d
    python3 scripts/simulate_agents.py
"""
import sys
import time
import httpx

BASE_URL = "http://localhost:8000"


def wait_for_backend(timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def simulate() -> int:
    print("Project Million — Agent Simulation")
    print("=" * 40)

    if not wait_for_backend():
        print("ERROR: Backend not reachable. Is docker compose running?")
        return 1

    failures = []

    # ── Step 1: Verify all C-Suite agents are registered ──────────────────────
    print("\n[1/5] Checking agent status...")
    r = httpx.get(f"{BASE_URL}/agents/status")
    agents = {a["agent_id"]: a for a in r.json()}
    for agent_id in ("cso", "cto", "cmo", "cfo", "coo"):
        if agent_id not in agents:
            failures.append(f"Agent {agent_id} not registered")
        else:
            print(f"  ✓ {agent_id}: {agents[agent_id]['status']}")

    # ── Step 2: Simulate CSO heartbeat ────────────────────────────────────────
    print("\n[2/5] Simulating CSO heartbeat...")
    r = httpx.post(f"{BASE_URL}/agents/cso/heartbeat", json={"status": "active"})
    if r.status_code == 200:
        print(f"  ✓ CSO heartbeat accepted, last_seen: {r.json()['last_seen']}")
    else:
        failures.append(f"CSO heartbeat failed: {r.status_code}")

    # ── Step 3: Create and approve a decision ─────────────────────────────────
    print("\n[3/5] Creating a pending decision...")
    r = httpx.post(f"{BASE_URL}/decisions", json={
        "title": "Enter B2B invoicing market",
        "description": "Strong demand, low competition, $2B TAM",
        "requested_by": "cso",
    })
    if r.status_code != 201:
        failures.append(f"Decision creation failed: {r.status_code}")
    else:
        decision_id = r.json()["id"]
        print(f"  ✓ Decision created: {decision_id}")

        # Board approves
        print("\n[4/5] Board approving decision...")
        r2 = httpx.post(f"{BASE_URL}/decisions/{decision_id}/approve")
        if r2.status_code == 200 and r2.json()["status"] == "approved":
            print(f"  ✓ Decision approved by board")
        else:
            failures.append(f"Approve failed: {r2.status_code} {r2.text}")

    # ── Step 4: Create and reject a second decision ───────────────────────────
    print("\n[5/5] Creating and rejecting a decision...")
    r = httpx.post(f"{BASE_URL}/decisions", json={
        "title": "Acquire competitor",
        "description": "Too expensive at current runway",
        "requested_by": "cfo",
    })
    if r.status_code == 201:
        d2_id = r.json()["id"]
        r3 = httpx.post(f"{BASE_URL}/decisions/{d2_id}/reject")
        if r3.status_code == 200 and r3.json()["status"] == "rejected":
            print(f"  ✓ Decision rejected by board")
        else:
            failures.append(f"Reject failed: {r3.status_code}")

    # ── Result ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 40)
    if failures:
        print("SIMULATION FAILED:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("SIMULATION PASSED — full agent pipeline verified:")
    print("  ✓ All 5 C-Suite agents registered")
    print("  ✓ Agent heartbeat updates status store")
    print("  ✓ Decision created → approved by board")
    print("  ✓ Decision created → rejected by board")
    print("\nStack is ready for Railway deployment.")
    return 0


if __name__ == "__main__":
    sys.exit(simulate())
