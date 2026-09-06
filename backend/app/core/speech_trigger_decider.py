"""言语触发决策器（问题1）★

取消「落子=必说话」绑定：按强/弱事件概率决定是否开口。
问题13：进一步压低开口频率，像真人——强事件(将军/吃子/绝杀/局势大幅波动)
60% 触发点评；弱事件(平淡招法) 8%；8 秒发言冷却避免连续喋喋不休；
连续 10 步静默才强制保底一句，防止整局哑巴。
不需要说话时仅播放数字人思考动画、静默思索。
"""
from __future__ import annotations

import random
import time

STRONG_PROB = 0.60   # 强事件触发点评概率（问题13：0.85 -> 0.60）
WEAK_PROB = 0.08     # 弱事件触发点评概率（问题13：0.15 -> 0.08）
COOLDOWN_SECONDS = 8.0  # 问题13：4.5s -> 8s
SILENT_STREAK_MAX = 10  # 问题13：8 -> 10 步


def classify_strength(
    *,
    events: list[str],
    user_move_captured: bool = False,
    ai_move_captured: bool = False,
    win_probability: float | None = None,
    prev_win_probability: float | None = None,
) -> bool:
    """True=强事件，False=弱事件（普通挪子/平卒/飞相等平淡招法）。"""
    if events:
        return True  # 将军 / 吃子 / 将死 / 困毙 均为强事件
    if user_move_captured or ai_move_captured:
        return True
    if win_probability is not None and prev_win_probability is not None:
        if abs(win_probability - prev_win_probability) >= 0.15:
            return True  # 局势大幅波动
    return False


def should_speak(
    *,
    is_strong: bool,
    last_speech_ts: float | None = None,
    silent_streak: int = 0,
    now: float | None = None,
) -> bool:
    """是否开口：强事件 60% / 弱事件 8%；8s 冷却内静默；连续 10 步静默强制保底。"""
    now = time.time() if now is None else now
    if last_speech_ts is not None and (now - last_speech_ts) < COOLDOWN_SECONDS:
        return False  # 冷却：避免连续喋喋不休
    if silent_streak >= SILENT_STREAK_MAX:
        return True  # 保底：整局不哑巴
    prob = STRONG_PROB if is_strong else WEAK_PROB
    return random.random() < prob
