"""FastAPI 应用入口：适老化数字人中国象棋棋友（OS2026）。

启动：uvicorn backend.app.main:app --reload
- API 与前端静态页面同源：http://127.0.0.1:8000/ 直接是棋盘页面
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import get_settings
from .db.database import init_db

SETTINGS = get_settings()
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="适老化数字人中国象棋棋友",
    description="OS2026 魔珐星云企业命题：具身交互智能创新应用（后端 + 前端）",
    version="0.2.0",
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


@app.get("/api/info")
def info() -> dict:
    return {
        "name": "适老化数字人中国象棋棋友",
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/health",
        "llm_mode": "mock" if SETTINGS.llm_configured is False else "real",
        "digital_human_enabled": SETTINGS.enable_digital_human,
    }


@app.websocket("/ws/game/{game_id}")
async def ws_game(ws: WebSocket, game_id: str):
    """对局 WebSocket：接收前端事件，回推数字人指令 / 棋局事件（脚手架）。"""
    await ws.accept()
    try:
        await ws.send_json({"game_id": game_id, "type": "connected"})
        while True:
            data = await ws.receive_text()
            await ws.send_json({"game_id": game_id, "type": "event", "payload": data})
    except WebSocketDisconnect:
        return


# 静态前端（最后挂载，/api /health 等路由优先）
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
