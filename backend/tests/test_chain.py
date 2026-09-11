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


def test_personality_locked_after_first_move():
    """问题7：对局一旦开始（已有任何着法）人格锁定，仅开局前可选。"""
    from backend.app.api import routes

    g = client.post("/api/games", json={"user_id": "u-plock", "personality": "laozhang"}).json()
    # 开局前（未走子）允许切换
    r0 = client.post(f"/api/games/{g['game_id']}/personality", json={"personality": "xiaoya"})
    assert r0.status_code == 200
    assert r0.json()["personality"] == "xiaoya"
    # 走一手
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
    mv = legal["moves"][0]
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-plock", "from_sq": mv["from"], "to_sq": mv["to"]},
    )
    assert r.status_code == 200
    # 走子后锁定 -> 400
    r2 = client.post(f"/api/games/{g['game_id']}/personality", json={"personality": "laozhang"})
    assert r2.status_code == 400
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


def test_checkmate_detected_win_directly(monkeypatch):
    """绝杀判赢：玩家一手将死 AI 时直接判胜（result=win + game_over），无需再吃老将。

    构造合法将死局面（卧槽马杀：红车 h9→e9 将死黑将，黑无合法应手），
    全链路验证：AI 无着法（from_sq=None）时后端按 position_status 判将死并终局。
    """
    from backend.app.api import routes

    monkeypatch.setattr(routes._settings, "speech_trigger_enabled", False)
    g = client.post("/api/games", json={"user_id": "u-mate", "personality": "laozhang"}).json()
    # 直接置为"红方一手杀"局面：车 h9->e9 后 卧槽马(马 f2) + 车 双将，黑将无路可逃
    routes._sessions[g["game_id"]]["fen"] = "4k1R2/5p3/5N3/9/9/9/9/9/9/3K3R1 w - - 0 1"
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-mate", "from_sq": "h9", "to_sq": "e9"},
    )
    assert r.status_code == 200
    body = r.json()
    # 关键：将死即终局，不必吃掉对方老将
    assert body["result"] == "win"
    assert body["game_over"] is True
    assert any("将死" in e and "AI" in e for e in body["events"])
    assert body["ai_move"]["from_sq"] is None  # AI 无合法应手（被将死）
    # 终局后再落子应 400
    r2 = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-mate", "from_sq": "h9", "to_sq": "e9"},
    )
    assert r2.status_code == 400
    routes._sessions.pop(g["game_id"], None)


def test_game_over_forces_ending_speech(monkeypatch):
    """结局必开口：将死终局绕过随机言语触发，数字人强制说祝贺收尾（LLM 生成）。"""
    from backend.app.api import routes

    monkeypatch.setattr(routes._settings, "speech_trigger_enabled", True)

    def fake_chat(messages):
        # 断言 Prompt 里注入了本局结果指令
        joined = "\n".join(m.get("content", "") for m in messages)
        assert "你获胜了" in joined
        return {"speech_text": "你赢了！这盘真漂亮。", "emotion_tag": "喜悦", "action_tag": "applaud"}

    monkeypatch.setattr(routes._llm, "chat", fake_chat)
    g = client.post("/api/games", json={"user_id": "u-ending", "personality": "laozhang"}).json()
    routes._sessions[g["game_id"]]["fen"] = "4k1R2/5p3/5N3/9/9/9/9/9/9/3K3R1 w - - 0 1"
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-ending", "from_sq": "h9", "to_sq": "e9"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "win" and body["game_over"] is True
    # 结局必开口：avatar_command 有台词且是祝贺
    assert body["avatar_command"] is not None
    assert "赢" in body["avatar_command"]["speech_text"]
    routes._sessions.pop(g["game_id"], None)


def test_game_over_ending_fallback_when_llm_empty(monkeypatch):
    """结局兜底：LLM 输出为空时回退人格固定收尾台词（保证'你赢了'必说）。"""
    from backend.app.api import routes

    monkeypatch.setattr(routes._settings, "speech_trigger_enabled", True)
    monkeypatch.setattr(
        routes._llm, "chat", lambda messages: {"speech_text": "", "emotion_tag": "平静", "action_tag": "idle"}
    )
    g = client.post("/api/games", json={"user_id": "u-ending2", "personality": "laozhang"}).json()
    routes._sessions[g["game_id"]]["fen"] = "4k1R2/5p3/5N3/9/9/9/9/9/9/3K3R1 w - - 0 1"
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-ending2", "from_sq": "h9", "to_sq": "e9"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "win"
    assert body["avatar_command"]["speech_text"] == routes._ENDING_LINES["laozhang"]["win"]
    routes._sessions.pop(g["game_id"], None)


def test_chat_echo_tail_ignored():
    """录音尾音兜底：数字人刚说完（3s 内），识别文本是其台词后缀/子串 -> 判噪音丢弃。"""
    import time as _time

    from backend.app.api import routes

    g = client.post("/api/games", json={"user_id": "u-echo", "personality": "laozhang"}).json()
    sess = routes._sessions[g["game_id"]]
    sess["last_ai_speech"] = "这盘下得有味儿"
    sess["last_speech_ts"] = _time.time()
    # 尾音后缀 -> 丢弃
    r = client.post("/api/chat", json={"game_id": g["game_id"], "user_id": "u-echo", "text": "得有味儿"})
    assert r.status_code == 200
    assert r.json()["status"] == "noise_ignored"
    # 正常输入不受影响
    r2 = client.post("/api/chat", json={"game_id": g["game_id"], "user_id": "u-echo", "text": "今天天气不错"})
    assert r2.json()["status"] == "ok"
    routes._sessions.pop(g["game_id"], None)


def test_profile_endpoint():
    r = client.get("/api/profiles/u-test-3")
    assert r.status_code == 200
    assert "nickname" in r.json()["profile"]


def test_narrative_plays_through_avatar(monkeypatch):
    """问题4+问题13：主动叙事台词真正进入 avatar_command 播放链路（而非只入记忆）。

    强制关闭 LLM 点评（should_speak=False -> speak_now=False），连走 6 手
    （NARRATIVE_INTERVAL_MOVES=6），第 6 手必触发一次主动叙事；断言其
    narrative.text 非空，且 avatar_command.speech_text == narrative.text。
    """
    from backend.app.api import routes

    monkeypatch.setattr(routes._settings, "speech_trigger_enabled", True)
    monkeypatch.setattr(routes, "should_speak", lambda **kw: False)  # 永不 LLM 点评
    g = client.post("/api/games", json={"user_id": "u-narr", "personality": "laozhang"}).json()
    fen = g["fen"]
    fired = None
    for _ in range(6):
        legal = client.get("/api/moves/legal", params={"fen": fen, "color": "red"}).json()
        assert legal["moves"]
        mv = legal["moves"][0]
        r = client.post(
            "/api/moves",
            json={"game_id": g["game_id"], "user_id": "u-narr", "from_sq": mv["from"], "to_sq": mv["to"]},
        )
        assert r.status_code == 200
        body = r.json()
        fen = body["new_fen"]
        if body.get("narrative") and body["narrative"].get("text"):
            fired = body
    assert fired is not None, "连走 6 手后应触发至少一次主动叙事"
    n = fired["narrative"]
    assert n["text"]  # 台词非空
    # 关键：主动叙事台词必须真正进入数字人播放链路（avatar_command）
    assert fired["avatar_command"] is not None
    assert fired["avatar_command"]["speech_text"] == n["text"]
    assert fired["llm_output"] is None  # 主动叙事发生在静默（非 LLM 点评）分支
    routes._sessions.pop(g["game_id"], None)
