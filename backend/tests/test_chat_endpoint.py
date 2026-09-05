"""步骤4：语音输入闭环 —— POST /api/chat 对话端点。"""
from fastapi.testclient import TestClient

from backend.app.db.database import init_db
from backend.app.main import app

init_db()  # 确保测试库完成迁移（TestClient 无上下文时 lifespan 不触发）
client = TestClient(app)


def _new_game(uid):
    g = client.post("/api/games", json={"user_id": uid}).json()
    return g["game_id"]


def test_chat_noise_ignored():
    gid = _new_game("u-chat-noise")
    r = client.post("/api/chat", json={"game_id": gid, "user_id": "u-chat-noise", "text": "。。。"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "noise_ignored"
    assert body["reply"] is None
    from backend.app.api import routes
    routes._sessions.pop(gid, None)


def test_chat_normal_reply():
    gid = _new_game("u-chat-ok")
    r = client.post("/api/chat", json={"game_id": gid, "user_id": "u-chat-ok", "text": "你好呀，今天天气不错"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    reply = body["reply"]
    assert reply["speech_text"]
    assert reply["emotion_tag"] in ("平静", "喜悦", "惋惜", "惊讶", "赞赏", "鼓励", "沉思", "得意")
    assert reply["action_tag"] in ("nod", "smile", "frown", "applaud", "lean", "wave", "shrug", "idle")
    from backend.app.api import routes
    routes._sessions.pop(gid, None)


def test_chat_remembers_user_turn():
    """用户说的话入短期记忆，AI 回复入记忆。"""
    gid = _new_game("u-chat-mem")
    client.post("/api/chat", json={"game_id": gid, "user_id": "u-chat-mem", "text": "我叫李大爷"})
    from backend.app.api import routes
    sess = routes._sessions[gid]
    roles = [t.role for t in sess["memory"].short_term.turns]
    assert "user" in roles
    assert "assistant" in roles
    # 用户消息内容被记录
    texts = [t.content for t in sess["memory"].short_term.turns if t.role == "user"]
    assert any("李大爷" in t for t in texts)
    routes._sessions.pop(gid, None)


def test_chat_dedup_consecutive():
    """连续消息只响应最新（去抖窗口内后一条覆盖前一条）。"""
    gid = _new_game("u-chat-dd")
    client.post("/api/chat", json={"game_id": gid, "user_id": "u-chat-dd", "text": "第一步"})
    client.post("/api/chat", json={"game_id": gid, "user_id": "u-chat-dd", "text": "第二步最新"})
    from backend.app.api import routes
    sess = routes._sessions[gid]
    user_texts = [t.content for t in sess["memory"].short_term.turns if t.role == "user"]
    assert any("第二步最新" in t for t in user_texts)
    routes._sessions.pop(gid, None)
