"""问题4：主动叙事框架（占位）—— 决策器真实判断 + 内容生成占位静默。"""
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


def test_build_narrative_placeholder_empty():
    """叙事内容生成器为占位：默认返回空串，不打断对局。"""
    for t in NarrativeType:
        assert build_narrative(t, NarrativeContext()) == ""


def test_after_event_narrative_type():
    ctx = NarrativeContext(move_index=8, quiet_seconds=1.0, has_event=True)
    assert narrate(ctx) == NarrativeType.AFTER_EVENT
