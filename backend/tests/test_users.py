"""多用户账号 / 执黑 / 棋谱加精删除 / 模型管理。"""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_user_crud_and_login():
    r = client.post("/api/users", json={"nickname": "李大爷"})
    assert r.status_code == 200
    u = r.json()
    assert u["user_id"] and u["nickname"] == "李大爷"
    # 同昵称复用
    r2 = client.post("/api/users", json={"nickname": "李大爷"})
    assert r2.json()["user_id"] == u["user_id"]
    # 列表
    ids = [x["user_id"] for x in client.get("/api/users").json()["users"]]
    assert u["user_id"] in ids
    # 登录
    assert client.post("/api/users/login", json={"user_id": u["user_id"]}).status_code == 200
    assert client.post("/api/users/login", json={"user_id": "nope"}).status_code == 404
    # 改名
    rn = client.patch(f"/api/users/{u['user_id']}", json={"nickname": "李大爷改"})
    assert rn.status_code == 200 and rn.json()["nickname"] == "李大爷改"


def test_new_game_black_side_ai_opening():
    g = client.post(
        "/api/games",
        json={"user_id": "u-black", "side": "black", "strength": "high", "personality": "xiaoya"},
    ).json()
    assert g["side"] == "black"
    assert g["strength"] == "high"
    assert g["ai_opening"] and g["ai_opening"]["from_sq"] and g["ai_opening"]["to_sq"]
    # 轮到黑方(玩家)行棋
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "black"}).json()
    assert legal["moves"]
    from backend.app.api import routes
    routes._sessions.pop(g["game_id"], None)


def test_make_move_as_black():
    g = client.post("/api/games", json={"user_id": "u-black2", "side": "black"}).json()
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "black"}).json()
    mv = legal["moves"][0]
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-black2", "from_sq": mv["from"], "to_sq": mv["to"]},
    )
    assert r.status_code == 200
    body = r.json()
    # 用户走的是黑方(小写)棋子，AI 应手为红方(大写)棋子
    assert body["user_move"]["piece"].islower()
    assert body["ai_move"]["from_sq"] and body["ai_move"]["piece"].isupper()
    from backend.app.api import routes
    routes._sessions.pop(g["game_id"], None)


def test_game_star_and_delete():
    uid = "u-star"
    g = client.post("/api/games", json={"user_id": uid}).json()
    gid = g["game_id"]
    # 加精
    r = client.post(f"/api/games/{gid}/star", json={"starred": True})
    assert r.status_code == 200 and r.json()["starred"] is True
    games = client.get("/api/games", params={"user_id": uid}).json()["games"]
    mine = next(x for x in games if x["game_id"] == gid)
    assert mine["starred"] is True
    # 删除
    d = client.delete(f"/api/games/{gid}")
    assert d.status_code == 200
    games2 = client.get("/api/games", params={"user_id": uid}).json()["games"]
    assert all(x["game_id"] != gid for x in games2)
    from backend.app.api import routes
    routes._sessions.pop(gid, None)


def test_models_endpoints():
    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    assert body["models"] and body["current"]
    assert any(m["current"] for m in body["models"])
    # 切到第二个模型
    target = body["models"][1]["id"]
    r2 = client.post("/api/models", json={"model": target})
    assert r2.status_code == 200 and r2.json()["model"] == target
    # 未知模型 400
    assert client.post("/api/models", json={"model": "nope"}).status_code == 400


def test_delete_user_removes_data():
    uid = "u-account-del"
    client.post("/api/users", json={"nickname": "待删账号"})
    g = client.post("/api/games", json={"user_id": uid}).json()
    gid = g["game_id"]
    uid2 = g["user_id"]
    # 该测试用自动生成的 user_id（users 表无记录也可删除）
    r = client.delete(f"/api/users/{uid2}")
    assert r.status_code == 200
    games = client.get("/api/games", params={"user_id": uid2}).json()["games"]
    assert games == []
