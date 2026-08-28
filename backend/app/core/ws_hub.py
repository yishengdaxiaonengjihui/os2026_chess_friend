"""WebSocket 事件中心（自研核心，第三阶段）。

按 game_id 维护前端 WS 连接集合，支持从同步/异步代码广播事件：
- 数字人状态（thinking / speaking / idle）
- 棋局事件（吃子 / 将军 / 胜负）
设计上保证发送失败不影响主流程（发送是尽力而为）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_hubs: dict[str, set] = {}          # game_id -> {WebSocket, ...}
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """由应用 lifespan 注入运行中的事件循环，供同步代码调度协程。"""
    global _loop
    _loop = loop


def get_loop() -> Optional[asyncio.AbstractEventLoop]:
    """返回注入的事件循环（可能为 None，例如未启动 lifespan 的测试环境）。"""
    return _loop


def register(game_id: str, ws: Any) -> None:
    _hubs.setdefault(game_id, set()).add(ws)


def unregister(game_id: str, ws: Any) -> None:
    conns = _hubs.get(game_id)
    if conns:
        conns.discard(ws)
        if not conns:
            _hubs.pop(game_id, None)


def _send(ws: Any, payload: dict[str, Any]) -> None:
    """尽力发送：优先在事件循环上调度，失败仅记日志。"""
    if _loop is None or _loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(ws.send_json(payload), _loop)
    except Exception:  # noqa: BLE001
        logger.debug("WS 发送失败（连接可能已关闭）", exc_info=True)


def broadcast(game_id: str, payload: dict[str, Any]) -> None:
    for ws in list(_hubs.get(game_id, ())):
        _send(ws, payload)


def broadcast_avatar_state(game_id: str, state: str, command: Optional[dict[str, Any]] = None) -> None:
    broadcast(game_id, {"type": "avatar_state", "state": state, "command": command})


def broadcast_game_event(game_id: str, event: str) -> None:
    broadcast(game_id, {"type": "game_event", "event": event})
