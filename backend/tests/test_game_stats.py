"""对局统计与画像生成模块的单元测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import game_stats as gs


def test_detect_opening():
    assert gs.detect_opening({"piece": "C", "to": "e5"}) == "中炮开局"
    assert gs.detect_opening({"piece": "C", "to": "c5"}) == "边炮开局"
    assert gs.detect_opening({"piece": "P", "to": "a5"}) == "仙人指路"
    assert gs.detect_opening({"piece": "N", "to": "c6"}) == "屏风马开局"
    assert gs.detect_opening({"piece": "R", "to": "a5"}) == "直车开局"
    assert gs.detect_opening(None) == "未知"


def test_classify_style():
    # 样本不足 -> 待观察
    assert gs.classify_style({"moves": 4, "user_captures": 1}) == "待观察"
    # 高吃子率 -> 进攻型
    assert gs.classify_style({"moves": 10, "user_captures": 3}) == "进攻型"
    # 低吃子率 -> 防守型
    assert gs.classify_style({"moves": 10, "user_captures": 0}) == "防守型"
    # 中间 -> 稳健型
    assert gs.classify_style({"moves": 10, "user_captures": 1}) == "稳健型"


def test_estimate_strength():
    assert gs.estimate_strength(None) == "待观察"
    assert gs.estimate_strength(0.6) == "较强"
    assert gs.estimate_strength(0.5) == "中级"
    assert gs.estimate_strength(0.3) == "初级"


def test_update_live_stats():
    stats = gs.fresh_stats()
    gs.update_live_stats(
        stats,
        {"from": "a6", "to": "a5", "piece": "P", "captured": "p"},
        {"from": "b0", "to": "c2", "piece": "n", "captured": None},
        0.45,
    )
    assert stats["moves"] == 1
    assert stats["user_captures"] == 1
    assert stats["ai_captures"] == 0
    assert stats["first_move"] == {"from": "a6", "to": "a5", "piece": "P"}
    assert stats["avg_user_win_prob"] == 0.45
    gs.update_live_stats(stats, {"from": "a5", "to": "a4", "piece": "P"}, None, 0.55)
    assert stats["moves"] == 2
    assert abs(stats["avg_user_win_prob"] - 0.5) < 1e-6


def test_finalize_and_style_diff():
    stats = gs.fresh_stats()
    for i in range(10):
        captured = "p" if i == 3 else None  # 10 手 1 吃子 -> 吃子率 0.1 -> 稳健型
        gs.update_live_stats(stats, {"from": "a6", "to": "a5", "piece": "P", "captured": captured}, None, 0.5)
    gs.finalize_game(stats, "win")
    assert stats["games"] == 1 and stats["wins"] == 1 and stats["losses"] == 0
    assert stats["openings"].get("仙人指路") == 1
    diff = gs.style_strength_diff(stats)
    assert diff["style"] == "稳健型" and diff["strength"] == "中级"
    summary = gs.build_game_summary(stats, "win")
    assert "执红取胜" in summary and "仙人指路" in summary
