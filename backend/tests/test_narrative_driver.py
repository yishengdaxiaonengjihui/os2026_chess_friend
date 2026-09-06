"""问题4+问题13：主动叙事节拍器 —— 决策器真实判断 + 简短口语台词 + 不打断事件。"""
import pytest

from backend.app.core.narrative_driver import (
    NarrativeContext,
    NarrativeType,
    build_narrative,
    narrate,
)


def test_opening_triggers_narrative():
    """对局开场（前几手）应触发开场叙事。"""
    ctx = NarrativeContext(move_index=1, is_opening=True)
    assert narrate(ctx) == NarrativeType.OPENING
    ctx2 = NarrativeContext(move_index=2, is_opening=False)
    assert narrate(ctx2) == NarrativeType.OPENING  # move_index<=2 仍视为开场


def test_quiet_triggers_narrative():
    """长时间静默应主动找话题（避免整局冷场）。"""
    ctx = NarrativeContext(move_index=5, quiet_seconds=45.0)
    assert narrate(ctx) == NarrativeType.QUIET
    # 长时间未到阈值时不主动叙事
    ctx2 = NarrativeContext(move_index=5, quiet_seconds=3.0)
    assert narrate(ctx2) == NarrativeType.NONE


def test_game_over_no_narrative():
    """终局不主动叙事。"""
    ctx = NarrativeContext(move_index=10, game_over=True, has_event=True)
    assert narrate(ctx) == NarrativeType.NONE


def test_after_event_not_interrupt():
    """关键事件后不主动插话（本步有 LLM 点评），避免叠话。"""
    ctx = NarrativeContext(move_index=8, quiet_seconds=1.0, has_event=True)
    assert narrate(ctx) == NarrativeType.NONE


def test_build_narrative_returns_short_lines():
    """叙事内容生成器只对 OPENING/QUIET 产出极短口语台词，其余静默。"""
    for t in (NarrativeType.OPENING, NarrativeType.QUIET):
        line = build_narrative(t, NarrativeContext())
        assert isinstance(line, str)
        assert 0 < len(line) <= 24  # 语气词级别，极短
    for t in (NarrativeType.NONE, NarrativeType.AFTER_EVENT):
        assert build_narrative(t, NarrativeContext()) == ""


def test_build_narrative_per_personality():
    """按人格取词库；未知人格回退老张。"""
    for personality in ("laozhang", "xiaoya", "unknown"):
        line = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality))
        assert isinstance(line, str) and line
