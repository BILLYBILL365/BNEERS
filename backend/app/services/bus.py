from typing import ClassVar
from fastapi import WebSocket
from app.schemas.events import BusEvent

class ConnectionManager:
    _instance: ClassVar["ConnectionManager | None"] = None

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    @classmethod
    def get(cls) -> "ConnectionManager":
        if cls._instance is None:
            cls._instance = ConnectionManager()
        return cls._instance

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: BusEvent):
        data = event.model_dump_json()
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_connections.remove(ws)

manager = ConnectionManager.get()
