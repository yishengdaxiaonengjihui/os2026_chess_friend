"""问题1：言语触发决策器 —— 取消“落子=必说话”，强/弱事件概率 + 冷却 + 保底。"""
import pytest

from backend.app.core.speech_trigger_decider import classify_strength, should_speak


def test_classify_strength():
    assert classify_strength(events=["将军：玩家被将军！"]) is True
    assert classify_strength(events=["玩家吃子：吃掉对方马"]) is True
    assert classify_strength(events=["将死：玩家被将死，AI 获胜"]) is True
    assert classify_strength(events=[], user_move_captured=True) is True
    assert classify_strength(events=[], ai_move_captured=True) is True
    assert classify_strength(events=[], win_probability=0.2, prev_win_probability=0.5) is True
    assert classify_strength(events=[]) is False
    assert classify_strength(events=[], win_probability=0.5, prev_win_probability=0.52) is False


def test_should_speak_cooldown_and_streak():
    # 8s 冷却内：即使强事件也静默（避免连续喋喋不休）
    assert should_speak(is_strong=True, last_speech_ts=100.0, now=100.1, silent_streak=0) is False
    # 冷却已过、弱事件：走概率分支（返回值必须是布尔）
    assert should_speak(is_strong=False, last_speech_ts=100.0, now=105.0, silent_streak=0) in (True, False)
    # 连续 10 步静默：保底强制开口（问题13：8 -> 10 步才保底）
    assert should_speak(is_strong=False, last_speech_ts=None, silent_streak=10) is True
    # 未到 10 步：走概率分支，不强制
    assert should_speak(is_strong=False, last_speech_ts=None, silent_streak=9) in (True, False)


def test_probability_branches(monkeypatch):
    monkeypatch.setattr("backend.app.core.speech_trigger_decider.random.random", lambda: 0.5)
    # 弱事件 8%：0.5 > 0.08 -> 不说话（问题13：15% -> 8%）
    assert should_speak(is_strong=False, last_speech_ts=None, silent_streak=0) is False
    # 强事件 60%：0.5 < 0.60 -> 说话（问题13：85% -> 60%）
    assert should_speak(is_strong=True, last_speech_ts=None, silent_streak=0) is True


def test_silent_move_returns_none_llm(monkeypatch):
    """集成：开启触发决策且随机不触发时，落子返回 llm_output=None（静默），不崩。"""
    from fastapi.testclient import TestClient

    from backend.app.api import routes
    from backend.app.main import app

    client = TestClient(app)
    monkeypatch.setattr(routes._settings, "speech_trigger_enabled", True)
    monkeypatch.setattr("backend.app.core.speech_trigger_decider.random.random", lambda: 1.0)
    g = client.post("/api/games", json={"user_id": "u-silent", "personality": "laozhang"}).json()
    legal = client.get("/api/moves/legal", params={"fen": g["fen"], "color": "red"}).json()
    mv = legal["moves"][0]
    r = client.post(
        "/api/moves",
        json={"game_id": g["game_id"], "user_id": "u-silent", "from_sq": mv["from"], "to_sq": mv["to"]},
    )
    assert r.status_code == 200
    assert r.json()["llm_output"] is None
    routes._sessions.pop(g["game_id"], None)
