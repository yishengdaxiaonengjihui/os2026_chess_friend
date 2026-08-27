"""全链路单测：健康检查 → 新对局 → 落子（mock LLM + mock 数字人）。"""
from fastapi.testclient import TestClient

from backend.app.core import chess_context_parser as ccp
from backend.app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "mock"  # conftest 强制 mock


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["digital_human_enabled"] is True


def test_new_game():
    r = client.post("/api/games", json={"user_id": "u-test-1", "personality": "laozhang"})
    assert r.status_code == 200
    body = r.json()
    assert body["game_id"]
    assert body["fen"] == ccp.make_default_fen()
    assert body["side"] == "w"


def test_move_chain():
    g = client.post("/api/games", json={"user_id": "u-test-2"}).json()
    fen = g["fen"]
    new_fen = ccp.apply_move_to_fen(fen, "a6", "a5")
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-test-2", "fen": new_fen, "from_sq": "a6", "to_sq": "a5"},
    )
    assert r.status_code == 200
    body = r.json()
    # 引擎 AI 应手
    assert body["ai_move"]["from_sq"] and body["ai_move"]["to_sq"]
    assert body["new_fen"] != new_fen
    assert body["events"] == [] or any("AI 吃子" in e for e in body["events"])
    # LLM + 数字人
    assert body["llm_output"]["speech_text"]
    assert body["avatar_command"]["action_tag"]
    assert body["long_term_memories"] == []
    assert "nickname" in body["profile"]


def test_profile_endpoint():
    r = client.get("/api/profiles/u-test-3")
    assert r.status_code == 200
    assert "nickname" in r.json()["profile"]
