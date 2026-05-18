from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from typing import List

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # We iterate over a copy of the list to safely remove disconnected ones
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

@router.websocket("/ws/market")
async def market_stream(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Just keep alive — backend pushes data, frontend only listens
            await asyncio.sleep(30)
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket)
        print("Frontend WebSocket disconnected")
