"""对局统计与画像生成模块（自研核心，第二阶段）★

把「下棋行为」沉淀为结构化画像 + 长期记忆：
- 开局识别（第一手棋 -> 开局名）
- 棋风分类（吃子率 -> 进攻 / 稳健 / 防守）
- 棋力估计（用户平均胜率 vs 引擎难度）
- 对局终结：胜负结果 -> 画像统计累加 + 长期记忆摘要

所有统计仅基于下棋行为，用于娱乐陪伴参考，不属于医疗/心理诊断。
"""
from __future__ import annotations

from typing import Any, Optional

_PIECE_NAMES = {
    "K": "帅", "A": "仕", "B": "相", "N": "马", "R": "车", "C": "炮", "P": "兵",
}


def fresh_stats() -> dict[str, Any]:
    """一份新的对局统计（跨对局累加存在 SQLite 画像的 stats 字段）。"""
    return {
        "games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "moves": 0,
        "user_captures": 0,
        "ai_captures": 0,
        "first_move": None,          # {"from","to","piece"}
        "openings": {},              # 开局名 -> 次数
        "avg_user_win_prob": None,
        "last_result": None,
    }


def detect_opening(first_move: Optional[dict]) -> str:
    """根据第一手棋识别开局类型（启发式，非穷举）。"""
    if not first_move:
        return "未知"
    piece = first_move.get("piece", "")
    to = first_move.get("to", "")
    to_file = to[0] if to else ""
    if piece in ("C", "c"):
        return "中炮开局" if to_file == "e" else "边炮开局"
    if piece in ("N", "n"):
        return "屏风马开局"
    if piece in ("P", "p"):
        return "仙人指路"
    if piece in ("B", "b"):
        return "飞相局"
    if piece in ("A", "a"):
        return "补士局"
    if piece in ("R", "r"):
        return "直车开局"
    return "常规开局"


def classify_style(stats: dict[str, Any]) -> str:
    """棋风分类：吃子率 >=12% 进攻型，<=4% 防守型，其余稳健型。"""
    moves = stats.get("moves", 0)
    if moves < 6:
        return "待观察"
    rate = stats.get("user_captures", 0) / max(moves, 1)
    if rate >= 0.12:
        return "进攻型"
    if rate <= 0.04:
        return "防守型"
    return "稳健型"


def estimate_strength(avg_user_win_prob: Optional[float]) -> str:
    """棋力估计：用户平均胜率（对 AI）。"""
    if avg_user_win_prob is None:
        return "待观察"
    if avg_user_win_prob >= 0.55:
        return "较强"
    if avg_user_win_prob >= 0.45:
        return "中级"
    return "初级"


def update_live_stats(
    stats: dict[str, Any],
    user_move: Optional[dict],
    ai_move: Optional[dict],
    win_prob: Optional[float],
) -> dict[str, Any]:
    """每手棋更新统计（画像逐步生成），返回更新后的 stats。"""
    stats["moves"] = stats.get("moves", 0) + 1
    if user_move and user_move.get("captured"):
        stats["user_captures"] = stats.get("user_captures", 0) + 1
    if ai_move and ai_move.get("captured"):
        stats["ai_captures"] = stats.get("ai_captures", 0) + 1
    if stats.get("first_move") is None and user_move:
        stats["first_move"] = {
            "from": user_move["from"],
            "to": user_move["to"],
            "piece": user_move["piece"],
        }
    if win_prob is not None:
        prev = stats.get("avg_user_win_prob")
        if prev is None:
            stats["avg_user_win_prob"] = round(win_prob, 4)
        else:
            moves = stats["moves"]
            stats["avg_user_win_prob"] = round((prev * (moves - 1) + win_prob) / moves, 4)
    return stats


def style_strength_diff(stats: dict[str, Any]) -> dict[str, Any]:
    """由统计推导 style / strength / opening（供画像 diff，非空字段）。"""
    diff: dict[str, Any] = {}
    style = classify_style(stats)
    strength = estimate_strength(stats.get("avg_user_win_prob"))
    opening = detect_opening(stats.get("first_move"))
    if style != "待观察":
        diff["style"] = style
    if strength != "待观察":
        diff["strength"] = strength
    if opening != "未知":
        diff["opening"] = opening
    return diff


def register_opening(stats: dict[str, Any], opening: str) -> None:
    openings = stats.setdefault("openings", {})
    openings[opening] = openings.get(opening, 0) + 1


def finalize_game(stats: dict[str, Any], result: str) -> dict[str, Any]:
    """对局结束：累加对局数/胜负/开局。result: 'win' | 'lose' | 'draw'。"""
    stats["games"] = stats.get("games", 0) + 1
    stats["last_result"] = result
    if result == "win":
        stats["wins"] = stats.get("wins", 0) + 1
    elif result == "lose":
        stats["losses"] = stats.get("losses", 0) + 1
    else:
        stats["draws"] = stats.get("draws", 0) + 1
    register_opening(stats, detect_opening(stats.get("first_move")))
    return stats


def build_game_summary(stats: dict[str, Any], result: str) -> str:
    """生成一条长期记忆摘要（对局结束后写入长期记忆）。"""
    result_text = {"win": "执红取胜", "lose": "执红惜败", "draw": "执红弈和"}.get(result, "结束对局")
    opening = detect_opening(stats.get("first_move"))
    style = classify_style(stats)
    strength = estimate_strength(stats.get("avg_user_win_prob"))
    return (
        f"用户完成一局中国象棋：{result_text}，采用{opening}，共走{stats.get('moves', 0)}手，"
        f"用户吃子{stats.get('user_captures', 0)}枚、被吃{stats.get('ai_captures', 0)}枚。"
        f"观察到棋风偏{style}、棋力{strength}。"
    )
