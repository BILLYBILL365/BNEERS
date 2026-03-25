import pytest
import json
import asyncio
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.models import Base
from app.database import get_db
from app.services.bus import ConnectionManager

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(autouse=True)
def reset_manager():
    # Reset singleton between tests
    ConnectionManager._instance = None
    yield
    ConnectionManager._instance = None

@pytest.mark.asyncio
async def test_websocket_connects():
    async with ASGIWebSocketTransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with aconnect_ws("/ws", client) as ws:
                msg = await ws.receive_text()
                data = json.loads(msg)
                assert data["type"] == "connected"

@pytest.mark.asyncio
async def test_websocket_receives_broadcast():
    async with ASGIWebSocketTransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with aconnect_ws("/ws", client) as ws:
                await ws.receive_text()  # consume welcome

                # Broadcast directly to test the WebSocket layer
                from app.services.bus import manager
                from app.schemas.events import BusEvent
                event = BusEvent(type="task.created", payload={"task_id": "test-123", "agent_id": "cto"})
                await manager.broadcast(event)

                msg = await asyncio.wait_for(ws.receive_text(), timeout=2.0)
                data = json.loads(msg)
                assert data["type"] == "task.created"
                assert data["payload"]["task_id"] == "test-123"

@pytest.mark.asyncio
async def test_task_creation_broadcasts_event():
    """POST /tasks should trigger a task.created WebSocket broadcast."""
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGIWebSocketTransport(app=app), base_url="http://test") as client:
            async with aconnect_ws("/ws", client) as ws:
                await ws.receive_text()  # consume welcome

                await client.post("/tasks", json={"title": "Build MVP", "agent_id": "cto"})

                msg = await asyncio.wait_for(ws.receive_text(), timeout=2.0)
                data = json.loads(msg)
                assert data["type"] == "task.created"
                assert data["payload"]["agent_id"] == "cto"
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
