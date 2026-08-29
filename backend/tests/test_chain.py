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


def test_root_serves_frontend():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "适老化数字人中国象棋棋友" in r.text


def test_api_info():
    r = client.get("/api/info")
    assert r.status_code == 200
    assert r.json()["digital_human_enabled"] is True


def test_legal_moves_endpoint():
    fen = ccp.make_default_fen()
    r = client.get("/api/moves/legal", params={"fen": fen, "color": "red"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["moves"]) > 0
    assert "from" in body["moves"][0] and "to" in body["moves"][0]


def test_new_game():
    r = client.post("/api/games", json={"user_id": "u-test-1", "personality": "laozhang"})
    assert r.status_code == 200
    body = r.json()
    assert body["game_id"]
    assert body["fen"] == ccp.make_default_fen()
    assert body["side"] == "red"
    assert body["strength"] == "auto"
    assert body["ai_opening"] is None


def test_move_chain():
    g = client.post("/api/games", json={"user_id": "u-test-2"}).json()
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
    assert legal["moves"]
    mv = legal["moves"][0]
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-test-2", "from_sq": mv["from"], "to_sq": mv["to"]},
    )
    assert r.status_code == 200
    body = r.json()
    # 引擎 AI 应手
    assert body["ai_move"]["from_sq"] and body["ai_move"]["to_sq"]
    assert body["user_move"]["from"] == mv["from"]
    assert body["user_move"]["to"] == mv["to"]
    assert body["new_fen"] != g["fen"]
    # LLM + 数字人
    assert body["llm_output"]["speech_text"]
    assert body["avatar_command"]["action_tag"]
    assert body["long_term_memories"] == []
    assert "nickname" in body["profile"]


def test_illegal_move_rejected():
    g = client.post("/api/games", json={"user_id": "u-illegal"}).json()
    # 非红方合法着法（a0 是黑车）-> 400
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-illegal", "from_sq": "a0", "to_sq": "a9"},
    )
    assert r.status_code == 400


def test_move_updates_profile_stats():
    from backend.app.api import routes
    from backend.app.core.memory_manager import ProfileStore

    ProfileStore().reset("u-stats")  # 隔离：清掉历史跨对局统计，保证 moves==1
    g = client.post("/api/games", json={"user_id": "u-stats"}).json()
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
    mv = legal["moves"][0]
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-stats", "from_sq": mv["from"], "to_sq": mv["to"]},
    )
    assert r.status_code == 200
    stats = r.json()["profile"]["stats"]
    assert stats["moves"] == 1
    assert stats["games"] == 0  # 未结束
    assert "first_move" in stats
    # 画像已持久化且开局已识别
    p = client.get("/api/profiles/u-stats").json()["profile"]
    assert p["opening"] in ("中炮开局", "边炮开局", "仙人指路", "屏风马开局", "飞相局", "补士局", "直车开局", "常规开局")
    # 清理该测试用户，避免污染后续测试
    routes._sessions.pop(g["game_id"], None)


def test_game_over_blocks_moves():
    from backend.app.api import routes

    g = client.post("/api/games", json={"user_id": "u-over"}).json()
    # 人为标记本局结束 -> 再落子应 400
    routes._sessions[g["game_id"]]["game_over"] = True
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
    mv = legal["moves"][0]
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-over", "from_sq": mv["from"], "to_sq": mv["to"]},
    )
    assert r.status_code == 400
    routes._sessions.pop(g["game_id"], None)


def test_profile_endpoint():
    r = client.get("/api/profiles/u-test-3")
    assert r.status_code == 200
    assert "nickname" in r.json()["profile"]
