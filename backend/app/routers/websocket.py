from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.schemas.events import BusEvent
from app.services.bus import manager

router = APIRouter(tags=["websocket"])

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    welcome = BusEvent(type="connected", payload={"message": "Mission Control connected"})
    await websocket.send_text(welcome.model_dump_json())
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
