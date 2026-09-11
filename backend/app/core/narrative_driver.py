"""主动叙事框架（问题4 + 问题13）★ —— 参考 ProactiveAgent 的"节拍器"思想。

目标：让数字人棋友在合适的时机**主动**讲点小故事 / 抛个话题，
而不只是被动回应棋局事件。参考 ProactiveAgent（scheduler + sleep_time
calculator）：大部分时间"休眠"，只有在经过一段安静间隔、且没有
强事件打断时，才主动"醒来"说一句简短家常话。

设计：
- narrate() 决策器：判断当前是否该主动叙事（对局开场、长时间静默），
  并给出叙事类型。
- build_narrative() 内容生成器：按类型返回 {text, emotion_tag, action_tag}。
  - OPENING：开场打招呼（喜悦/挥手）。
  - QUIET：优先讲人格 stories（短回忆，personas.json 已口语化），按本回合
    事件关键词挑最贴合的一条（吃子/将军/马/车），支持会话内去重；没有
    故事时回退语气词库。
- 节拍：由调用方（routes）按手数间隔限频，避免 12 手后每手都主动说。
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum

from .persona_store import stories as persona_stories


class NarrativeType(str, Enum):
    OPENING = "opening"     # 对局开场：打声招呼、聊聊近况
    QUIET = "quiet"         # 长时间静默：主动找话题
    AFTER_EVENT = "after_event"  # 关键事件后（吃子/将军/胜负）
    NONE = "none"           # 不该叙事


@dataclass
class NarrativeContext:
    """叙事决策上下文。"""
    move_index: int = 0
    game_over: bool = False
    is_opening: bool = False          # 开局阶段（前 N 手）
    quiet_seconds: float = 0.0        # 距离上次 AI 开口的秒数
    has_event: bool = False           # 本回合是否有强事件（吃子/将军等）
    personality: str = "laozhang"
    events: list[str] = field(default_factory=list)  # 本回合事件（供故事匹配）
    exclude: set[str] = field(default_factory=set)   # 已讲过的片段（会话内去重）


# 触发阈值（可配置）
OPENING_MOVES = 3             # 前 3 手视为开场
QUIET_TRIGGER_SECONDS = 45.0  # 静默超过 45s 才主动找话题（问题13：30->45）
QUIET_TRIGGER_MOVES = 10      # 连续多手无话也主动找话题
NARRATIVE_INTERVAL_MOVES = 6  # 主动叙事最少间隔手数（节拍器频率）


# 简短家常语气词库（极短、口语化、不机械、不用“你/您”称呼）——问题13：只给
# 语气词级别；仅在没有 stories 时作为兜底。
_QUIET_LINES = {
    "laozhang": [
        "嗯，这盘下得有味儿。",
        "看看，走得挺稳。",
        "好，慢慢下。",
        "嗯，有点意思。",
    ],
    "xiaoya": [
        "嗯嗯，这盘挺有意思的。",
        "看看，下得很稳呢。",
        "好呀，慢慢下。",
        "嗯，越来越有味道了。",
    ],
}

_OPENING_LINES = {
    "laozhang": [
        "嘿，来一局，坐稳喽。",
        "好，开局了，咱慢慢下。",
    ],
    "xiaoya": [
        "好呀，开局咯，慢慢下。",
        "嗯，开始了，慢慢来哦。",
    ],
}

# 回忆片段可用的情绪/动作（讲往事偏沉思；得意内容另判）
_STORY_EMOTIONS = ("沉思", "平静")
_STORY_ACTIONS = ("idle", "nod", "smile")
# 得意内容关键词 -> 情绪/动作
_PROUD_WORDS = ("全赢", "赢过来", "够劲儿", "厉害", "心服口服")


def _lines_for(personality: str, kind: str) -> list[str]:
    table = _OPENING_LINES if kind == "opening" else _QUIET_LINES
    return table.get(personality, table["laozhang"])


def _match_story(snips: list[str], events: list[str]) -> list[str]:
    """按本回合事件关键词挑最贴合的回忆片段；无事件/无命中返回原列表（随机）。

    轻量规则：事件含"吃"-> 挑带"吃/收/赢"的片段；含"将"-> 挑带"将/赢/全国"；
    含"马"-> 挑带"马/盲棋"；含"车"-> 挑带"车轮/车"。命中即视为"在讲当下"。
    """
    if not events:
        return snips
    ev = "，".join(events)
    keys: list[str] = []
    if "吃" in ev:
        keys.extend(("吃", "收下", "赢"))
    if "将" in ev:
        keys.extend(("将", "赢", "全国", "棋王"))
    if "马" in ev:
        keys.extend(("马", "盲棋"))
    if "车" in ev:
        keys.extend(("车轮", "车"))
    if not keys:
        return snips
    hit = [s for s in snips if any(k in s for k in keys)]
    return hit or snips


def _story_emotion_action(text: str) -> tuple[str, str]:
    """按故事内容给情绪/动作：得意内容->得意/smile；回忆->沉思/平静 + 轻动作。"""
    if any(k in text for k in _PROUD_WORDS):
        return "得意", "smile"
    return random.choice(_STORY_EMOTIONS), random.choice(_STORY_ACTIONS)


def narrate(ctx: NarrativeContext, now: float | None = None) -> NarrativeType:
    """主动叙事决策器：返回建议的叙事类型。

    优先级：对局开场 > 长时间静默；关键事件后不主动插话（有 LLM 点评）；
    终局不主动叙事。真正的发言节奏由调用方按 NARRATIVE_INTERVAL_MOVES 限频。
    """
    if ctx.game_over:
        return NarrativeType.NONE
    # 开场：前几手打声招呼
    if ctx.is_opening or ctx.move_index <= OPENING_MOVES:
        return NarrativeType.OPENING
    # 长时间静默：主动找话题（避免整局冷场）
    quiet = ctx.quiet_seconds if ctx.quiet_seconds is not None else 0.0
    if quiet >= QUIET_TRIGGER_SECONDS or ctx.move_index >= QUIET_TRIGGER_MOVES:
        return NarrativeType.QUIET
    # 关键事件后：有 LLM 点评，不主动打断
    return NarrativeType.NONE


def build_narrative(n_type: NarrativeType, ctx: NarrativeContext) -> dict[str, str]:
    """叙事内容生成器：返回 {text, emotion_tag, action_tag}。

    只对 OPENING / QUIET 生成；其余返回空 text（不插话）。
    - OPENING：打招呼（喜悦/wave）。
    - QUIET：优先随机讲一条人格 stories（短回忆，真正"讲小故事"），按事件
      关键词匹配 + 会话内去重；stories 为空时回退语气词库。
    """
    if n_type == NarrativeType.OPENING:
        text = random.choice(_lines_for(ctx.personality, "opening"))
        return {"text": text, "emotion_tag": "喜悦", "action_tag": "wave"}
    if n_type == NarrativeType.QUIET:
        snips = persona_stories(ctx.personality)
        if snips:
            pool = _match_story(list(snips), list(ctx.events or []))
            told = set(ctx.exclude or set())
            fresh = [s for s in pool if s not in told]
            candidates = fresh or pool  # 全讲过则允许重复（避免无话可说）
            text = random.choice(candidates)
            emotion, action = _story_emotion_action(text)
            return {"text": text, "emotion_tag": emotion, "action_tag": action}
        return {
            "text": random.choice(_lines_for(ctx.personality, "quiet")),
            "emotion_tag": "平静",
            "action_tag": "idle",
        }
    return {"text": "", "emotion_tag": "平静", "action_tag": "idle"}
