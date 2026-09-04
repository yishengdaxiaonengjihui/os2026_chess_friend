"""主动叙事框架（问题4）★ —— 框架占位，可插拔。

目标：让数字人棋友在合适的时机**主动**讲点小故事 / 抛个话题，
而不只是被动回应棋局事件。本模块搭建框架：

- narrate() 决策器：判断当前是否该主动叙事（对局开场、长时间静默、
  关键事件后、对局结束等触发点），并给出叙事类型。
- build_narrative() 内容生成器：**占位** —— 默认返回空串（不打断对局），
  后续可接入 persona 外置故事 / Mem0 记忆，按叙事类型产出一句台词。

当前为占位实现：决策器有真实判断逻辑，内容生成默认静默，避免喧宾夺主。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class NarrativeType(str, Enum):
    OPENING = "opening"     # 对局开场：打声招呼、聊聊近况
    QUIET = "quiet"         # 长时间静默：主动找话题
    AFTER_EVENT = "after_event"  # 关键事件后（吃子/将军/胜负）
    NONE = "none"           # 不该叙事


@dataclass
class NarrativeContext:
    """叙事决策上下文（框架占位：字段先建好，后续按需扩展）。"""
    move_index: int = 0
    game_over: bool = False
    is_opening: bool = False          # 开局阶段（前 N 手）
    quiet_seconds: float = 0.0        # 距离上次 AI 开口的秒数
    has_event: bool = False           # 本回合是否有强事件（吃子/将军等）
    personality: str = "laozhang"


# 触发阈值（框架占位，可配置）
OPENING_MOVES = 2            # 前 2 手视为开场
QUIET_TRIGGER_SECONDS = 30.0  # 静默超过 30s 主动找话题
QUIET_TRIGGER_MOVES = 12      # 连续多手无话也主动找话题


def narrate(ctx: NarrativeContext, now: float | None = None) -> NarrativeType:
    """主动叙事决策器：返回建议的叙事类型。

    优先级：对局开场 > 长时间静默 > 关键事件后；终局不主动叙事。
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
    # 关键事件后：可借机叙个事（占位：默认不主动打断）
    if ctx.has_event:
        return NarrativeType.AFTER_EVENT
    return NarrativeType.NONE


def build_narrative(n_type: NarrativeType, ctx: NarrativeContext) -> str:
    """叙事内容生成器 —— 占位实现。

    当前统一返回空串（不实际插话）；后续接入 persona 外置故事 / Mem0
    记忆后，按 n_type 返回一句人格化的主动台词。
    """
    # 占位：框架就绪，内容默认静默，避免影响对局体验
    return ""
