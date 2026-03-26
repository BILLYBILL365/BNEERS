#!/usr/bin/env python3
"""
Staging smoke test for Project Million.

Usage:
    # Start the stack first:
    docker compose up -d
    # Wait for health:
    docker compose ps
    # Run this script:
    python3 scripts/staging_smoke_test.py
"""
import sys
import time
import httpx


BASE_URL = "http://localhost:8000"
MAX_WAIT_SECONDS = 60


def wait_for_backend(base_url: str, timeout: int) -> bool:
    """Poll /health until it returns 200 or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=2)
            if r.status_code == 200:
                return True
        except httpx.ConnectError:
            pass
        time.sleep(2)
    return False


def run_smoke_tests(base_url: str) -> list[str]:
    """Run all smoke test assertions. Returns list of failure messages."""
    failures = []

    # 1. Health check
    r = httpx.get(f"{base_url}/health")
    if r.status_code != 200:
        failures.append(f"GET /health returned {r.status_code}")
    elif r.json().get("status") != "ok":
        failures.append(f"GET /health body: {r.json()}")

    # 2. Agent status list — all 5 C-Suite agents should be present
    r = httpx.get(f"{base_url}/agents/status")
    if r.status_code != 200:
        failures.append(f"GET /agents/status returned {r.status_code}")
    else:
        agents = {a["agent_id"] for a in r.json()}
        for expected in ("cso", "cto", "cmo", "cfo", "coo"):
            if expected not in agents:
                failures.append(f"Agent '{expected}' missing from /agents/status")

    # 3. Decisions list — empty is fine, just must respond 200
    r = httpx.get(f"{base_url}/decisions")
    if r.status_code != 200:
        failures.append(f"GET /decisions returned {r.status_code}")

    # 4. Tasks list — empty is fine
    r = httpx.get(f"{base_url}/tasks")
    if r.status_code != 200:
        failures.append(f"GET /tasks returned {r.status_code}")

    return failures


def main() -> int:
    print(f"Waiting for backend at {BASE_URL} (up to {MAX_WAIT_SECONDS}s)...")
    if not wait_for_backend(BASE_URL, MAX_WAIT_SECONDS):
        print("ERROR: Backend did not become healthy in time.")
        return 1

    print("Backend is up. Running smoke tests...")
    failures = run_smoke_tests(BASE_URL)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("\nAll smoke tests passed:")
    print("  ✓ GET /health → {status: ok}")
    print("  ✓ GET /agents/status → all 5 C-Suite agents present")
    print("  ✓ GET /decisions → 200")
    print("  ✓ GET /tasks → 200")
    return 0


if __name__ == "__main__":
    sys.exit(main())
