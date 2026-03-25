import os
os.environ["TESTING"] = "true"

import pytest
from app.config import Settings

@pytest.fixture
def settings():
    return Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/projectmillion_test",
        REDIS_URL="redis://localhost:6379/1",
        SECRET_KEY="test-secret-key",
        TESTING=True,
    )
