"""FastAPI 应用入口：适老化数字人中国象棋棋友（OS2026）。

启动：uvicorn backend.app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .db.database import init_db

SETTINGS = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="适老化数字人中国象棋棋友",
    description="OS2026 魔珐星云企业命题：具身交互智能创新应用（后端）",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict:
    return {
        "name": "适老化数字人中国象棋棋友",
        "docs": "/docs",
        "health": "/health",
        "digital_human_enabled": SETTINGS.enable_digital_human,
    }


@app.websocket("/ws/game/{game_id}")
async def ws_game(ws: WebSocket, game_id: str):
    """对局 WebSocket：接收前端事件，回推数字人指令 / 棋局事件（第一版脚手架）。"""
    await ws.accept()
    try:
        await ws.send_json({"game_id": game_id, "type": "connected"})
        while True:
            data = await ws.receive_text()
            # 前端事件 → 会话调度层（落子/语音/打断）；第一阶段先回显，后续接编排链
            await ws.send_json({"game_id": game_id, "type": "event", "payload": data})
    except WebSocketDisconnect:
        return
