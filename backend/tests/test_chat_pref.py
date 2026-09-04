"""问题12：闲聊三档偏好 —— 安静 / 普通 / 爱聊天。"""
from fastapi.testclient import TestClient

from backend.app.core.prompt_builder import build_prompt, chat_pref_instruction
from backend.app.db.database import init_db
from backend.app.main import app

init_db()  # 确保测试库完成 chat_pref 等幂等迁移（TestClient 无上下文时 lifespan 不触发）
client = TestClient(app)


def test_chat_pref_instruction_mapping():
    assert "安静" in chat_pref_instruction("quiet")
    assert "普通" in chat_pref_instruction("balanced")
    assert "爱聊天" in chat_pref_instruction("chatty")
    # 未知取值回退普通
    assert "普通" in chat_pref_instruction("weird")


def test_build_prompt_injects_chat_pref():
    msgs = build_prompt(profile={}, chat_pref="quiet")
    assert "安静" in msgs[0]["content"]
    msgs2 = build_prompt(profile={}, chat_pref="chatty")
    assert "爱聊天" in msgs2[0]["content"]
    # 不传时不注入
    msgs3 = build_prompt(profile={})
    assert "闲聊偏好" not in msgs3[0]["content"]


def test_set_chat_pref_endpoint():
    uid = "u-pref12"
    client.post("/api/users", json={"nickname": "偏好测试"})
    # 先登录/创建拿到用户
    users = client.get("/api/users").json()["users"]
    u = next((x for x in users if x["nickname"] == "偏好测试"), None)
    assert u
    r = client.patch(f"/api/users/{u['user_id']}/chat-pref", json={"chat_pref": "chatty"})
    assert r.status_code == 200
    assert r.json()["chat_pref"] == "chatty"
    # 非法取值 -> 400
    r2 = client.patch(f"/api/users/{u['user_id']}/chat-pref", json={"chat_pref": "loud"})
    assert r2.status_code == 400


def test_new_game_carries_chat_pref():
    """开局时把用户的闲聊偏好快照进会话，供 Prompt 注入。"""
    from backend.app.api import routes

    users = client.get("/api/users").json()["users"]
    u = next((x for x in users if x["nickname"] == "偏好测试"), None)
    assert u
    client.patch(f"/api/users/{u['user_id']}/chat-pref", json={"chat_pref": "quiet"})
    g = client.post("/api/games", json={"user_id": u["user_id"]}).json()
    sess = routes._sessions[g["game_id"]]
    assert sess["chat_pref"] == "quiet"
    routes._sessions.pop(g["game_id"], None)
