"""第四批功能：送吃保护 / 人格切换 / 悔棋 / 棋谱库。"""
from fastapi.testclient import TestClient

from backend.app.core.chess_engine import legal_moves
from backend.app.main import app

client = TestClient(app)


def test_engine_legal_moves_filters_hanging_king():
    """送吃保护：走完老帅受攻的着法不再出现在合法着法里。"""
    fen = "4k4/9/4r4/9/9/9/9/4R4/9/4K4 w - - 0 1"
    moves = legal_moves(fen, "red")
    from_e7 = {m["to"] for m in moves if m["from"] == "e7"}
    assert "e8" in from_e7      # 继续挡线 -> 合法
    assert "f7" not in from_e7  # 移开挡线 -> 送吃，被过滤
    assert "g7" not in from_e7


def test_illegal_hanging_move_rejected():
    """送吃着法经 HTTP 返回 400 并带友好提示。"""
    g = client.post("/api/games", json={"user_id": "u-hang"}).json()
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-hang", "from_sq": "e7", "to_sq": "f7"},
    )
    # e7 在初始局面是空格（红方二路炮在 h7/b7），该着法本就非法 -> 400
    assert r.status_code == 400
    assert "送" in r.json()["detail"] or "走不得" in r.json()["detail"]
    from backend.app.api import routes
    routes._sessions.pop(g["game_id"], None)


def test_personality_switch():
    g = client.post("/api/games", json={"user_id": "u-pers"}).json()
    r = client.post(f"/api/games/{g['game_id']}/personality", json={"personality": "xiaoya"})
    assert r.status_code == 200
    assert r.json()["personality"] == "xiaoya"
    r2 = client.post(f"/api/games/{g['game_id']}/personality", json={"personality": "nope"})
    assert r2.status_code == 400
    from backend.app.api import routes
    routes._sessions.pop(g["game_id"], None)


def test_undo_flow():
    g = client.post("/api/games", json={"user_id": "u-undo"}).json()
    # 未走棋时悔棋 -> 400
    r = client.post(f"/api/games/{g['game_id']}/undo")
    assert r.status_code == 400

    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
    mv = legal["moves"][0]
    r1 = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-undo", "from_sq": mv["from"], "to_sq": mv["to"]},
    )
    assert r1.status_code == 200

    r2 = client.post(f"/api/games/{g['game_id']}/undo")
    assert r2.status_code == 200
    body = r2.json()
    assert body["fen"] == g["fen"]           # 回到本轮开始前
    assert body["move_index"] == 0
    assert body["game_over"] is False

    # 悔棋后可继续落子
    legal2 = client.get("/api/moves/legal", params={"fen": body["fen"], "color": "red"}).json()
    assert legal2["moves"]
    from backend.app.api import routes
    routes._sessions.pop(g["game_id"], None)



def test_resign_flow():
    """认输：判负、终局、棋谱记录 result=lose，且终局后不能再落子/再认输。"""
    from backend.app.api import routes

    uid = "u-resign"
    g = client.post("/api/games", json={"user_id": uid}).json()
    r = client.post(f"/api/games/{g['game_id']}/resign")
    assert r.status_code == 200
    body = r.json()
    assert body["game_over"] is True
    assert body["result"] == "lose"
    assert body["llm_output"]["speech_text"]

    # 终局后：再次认输 -> 400；落子 -> 400
    assert client.post(f"/api/games/{g['game_id']}/resign").status_code == 400
    assert client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": uid, "from_sq": "h7", "to_sq": "h3"},
    ).status_code == 400

    # 棋谱库记录 result=lose
    games = client.get("/api/games", params={"user_id": uid}).json()["games"]
    mine = next(x for x in games if x["game_id"] == g["game_id"])
    assert mine["result"] == "lose"
    routes._sessions.pop(g["game_id"], None)


def test_draw_offer():
    """和棋：AI 按局面判断，返回 accepted + 人格化台词；终局后不可再提。"""
    from backend.app.api import routes

    uid = "u-draw"
    g = client.post("/api/games", json={"user_id": uid}).json()
    r = client.post(f"/api/games/{g['game_id']}/draw")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["accepted"], bool)
    assert "user_win_prob" in body
    assert body["llm_output"]["speech_text"]
    if body["accepted"]:
        assert body["game_over"] is True
        # 终局后再提和棋 -> 400
        assert client.post(f"/api/games/{g['game_id']}/draw").status_code == 400
        # 棋谱库记录 result=draw
        games = client.get("/api/games", params={"user_id": uid}).json()["games"]
        mine = next(x for x in games if x["game_id"] == g["game_id"])
        assert mine["result"] == "draw"
    else:
        assert body["game_over"] is False
        # 未被同意 -> 仍可落子
        legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
        mv = legal["moves"][0]
        assert client.post(
            "/api/moves",
            json={"game_id": g["game_id"], "user_id": uid, "from_sq": mv["from"], "to_sq": mv["to"]},
        ).status_code == 200
    routes._sessions.pop(g["game_id"], None)

def test_games_library_endpoints():
    from backend.app.api import routes
    from backend.app.core.memory_manager import ProfileStore

    uid = "u-lib"
    ProfileStore().reset(uid)
    g = client.post("/api/games", json={"user_id": uid}).json()
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
    mv = legal["moves"][0]
    client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": uid, "from_sq": mv["from"], "to_sq": mv["to"]},
    )

    r = client.get("/api/games", params={"user_id": uid})
    assert r.status_code == 200
    games = r.json()["games"]
    assert any(x["game_id"] == g["game_id"] for x in games)
    assert games[0]["move_count"] >= 1

    r2 = client.get(f"/api/games/{g['game_id']}/moves")
    assert r2.status_code == 200
    moves = r2.json()["moves"]
    assert len(moves) == 1
    assert moves[0]["user_move"]["from"] == mv["from"]
    assert moves[0]["move_index"] == 1
    routes._sessions.pop(g["game_id"], None)
