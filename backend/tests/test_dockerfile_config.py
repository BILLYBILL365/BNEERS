"""Smoke tests that verify Docker and config are correctly set up."""
import json
import os
import shutil
import subprocess
import pytest


def test_backend_dockerfile_exists():
    """Dockerfile must exist and be buildable — basic sanity check."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")
    backend_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    result = subprocess.run(
        ["docker", "build", "--no-cache", "-t", "project-million-backend-test", "."],
        capture_output=True,
        text=True,
        cwd=backend_dir,
        timeout=300,
    )
    assert result.returncode == 0, f"docker build failed:\n{result.stderr}"


def test_env_example_covers_all_settings_fields():
    """Every required Settings field must appear in .env.example."""
    env_example_path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.env.example")
    )
    with open(env_example_path) as f:
        content = f.read()

    # These fields have no default in Settings and MUST be documented
    required_vars = [
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "ANTHROPIC_API_KEY",
    ]
    for var in required_vars:
        assert var in content, f"{var} missing from .env.example"


def test_backend_railway_json_is_valid():
    # backend/tests/ → backend/railway.json (one level up)
    path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../railway.json")
    )
    with open(path) as f:
        data = json.load(f)
    assert data["deploy"]["healthcheckPath"] == "/health"
    assert "alembic upgrade head" in data["deploy"]["startCommand"]


def test_frontend_railway_json_is_valid():
    # backend/tests/ → backend/ → project root → frontend/railway.json
    path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../frontend/railway.json")
    )
    with open(path) as f:
        data = json.load(f)
    assert data["build"]["builder"] == "DOCKERFILE"


def test_railway_json_files_have_required_fields():
    """Both railway.json files must have build, deploy, healthcheck configured."""
    for rel_path, healthcheck_path in [
        # backend/tests/ → backend/railway.json (one level up)
        ("../railway.json", "/health"),
        # backend/tests/ → backend/ → project root → frontend/railway.json
        ("../../frontend/railway.json", "/"),
    ]:
        abs_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)
        )
        with open(abs_path) as f:
            data = json.load(f)

        assert "build" in data, f"{rel_path}: missing 'build' section"
        assert "deploy" in data, f"{rel_path}: missing 'deploy' section"
        assert data["deploy"]["healthcheckPath"] == healthcheck_path, \
            f"{rel_path}: wrong healthcheckPath"
        assert data["deploy"]["healthcheckTimeout"] == 120, \
            f"{rel_path}: healthcheckTimeout should be 120"
