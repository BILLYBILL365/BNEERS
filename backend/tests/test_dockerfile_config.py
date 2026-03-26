"""Smoke tests that verify Docker and config are correctly set up."""
import os
import subprocess
import pytest


def test_backend_dockerfile_exists():
    """Dockerfile must exist and be buildable — basic sanity check."""
    # backend/tests/ → backend/ (one level up, where Dockerfile lives)
    backend_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    result = subprocess.run(
        ["docker", "build", "--no-cache", "-t", "project-million-backend-test", "."],
        capture_output=True,
        text=True,
        cwd=backend_dir,
    )
    assert result.returncode == 0, f"docker build failed:\n{result.stderr}"
