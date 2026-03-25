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
def get_session_factory():
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session
