from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import get_settings


@lru_cache
def get_engine():
    s = get_settings()
    return create_async_engine(s.DATABASE_URL, echo=s.ENVIRONMENT == "development")


@lru_cache
def get_engine():
    s = get_settings()
    url = s.DATABASE_URL
    # Railway provides postgresql:// but asyncpg needs postgresql+asyncpg://
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, echo=s.ENVIRONMENT == "development")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session
