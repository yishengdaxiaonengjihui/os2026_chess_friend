"""第三阶段：对局 WebSocket 连接测试（connected / echo）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

from backend.app.main import app


def test_ws_connect_and_echo():
    """WS 握手回 connected，收发消息回 echo。"""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/game/ws-test-1") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert data["game_id"] == "ws-test-1"
            ws.send_text("hello")
            echo = ws.receive_json()
            assert echo["type"] == "echo"
            assert echo["payload"] == "hello"
