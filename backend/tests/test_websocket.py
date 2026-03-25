import pytest
import json
import asyncio
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from app.main import app
from app.services.bus import ConnectionManager

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
