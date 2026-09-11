"""问题4+问题13：主动叙事节拍器 —— 决策器真实判断 + 口语台词 + 不打断事件。"""
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
    """开场台词保持极短；其余类型（NONE/AFTER_EVENT）静默。"""
    d = build_narrative(NarrativeType.OPENING, NarrativeContext())
    assert isinstance(d, dict) and d["text"]
    assert 0 < len(d["text"]) <= 24  # 开场词，极短
    assert d["emotion_tag"] and d["action_tag"]
    for t in (NarrativeType.NONE, NarrativeType.AFTER_EVENT):
        assert build_narrative(t, NarrativeContext())["text"] == ""


def test_quiet_uses_persona_stories():
    """静默时优先讲人格 stories（短回忆片段，真正"讲小故事"）。"""
    from backend.app.core.persona_store import stories as persona_stories

    for personality in ("laozhang", "xiaoya"):
        d = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality))
        assert isinstance(d, dict) and d["text"]
        assert d["text"] in persona_stories(personality)
        assert d["emotion_tag"] in ("沉思", "平静", "得意")
        assert d["action_tag"] in ("idle", "nod", "smile")


def test_quiet_fallback_without_stories(monkeypatch):
    """人格没有 stories 时回退语气词库，不崩。"""
    from backend.app.core import narrative_driver as nd

    monkeypatch.setattr(nd, "persona_stories", lambda p: [])
    for personality in ("laozhang", "xiaoya", "unknown"):
        d = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality))
        assert isinstance(d, dict) and d["text"]


def test_build_narrative_per_personality():
    """按人格取词库/故事；未知人格回退老张。"""
    for personality in ("laozhang", "xiaoya", "unknown"):
        d = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality))
        assert isinstance(d, dict) and d["text"]


def test_quiet_story_matches_events():
    """故事按本回合事件关键词匹配：吃子时优先讲带'吃/赢'的回忆片段。"""
    for personality in ("laozhang", "xiaoya"):
        pool = []
        for _ in range(60):
            d = build_narrative(
                NarrativeType.QUIET,
                NarrativeContext(personality=personality, events=["玩家吃子：吃掉对方马"]),
            )
            assert d["text"]
            pool.append(d["text"])
        # 60 次中至少应出现一次贴合"吃"的片段（随机也可能全命中；这里保证可命中且合法）
        assert any(("吃" in s or "赢" in s) for s in pool)


def test_quiet_story_dedup_by_exclude():
    """会话内去重：已讲过的片段不再重复（排除集优先）。"""
    from backend.app.core.persona_store import stories as persona_stories

    snips = persona_stories("laozhang")
    told = set(snips)  # 全部讲过了 -> 允许回退到全量（不会无话可说）
    d = build_narrative(
        NarrativeType.QUIET,
        NarrativeContext(personality="laozhang", exclude=told),
    )
    assert d["text"] in snips
    # 只排除一条 -> 不会选到被排除的那条（除非它以外全是排除）
    one = snips[0]
    other = set(snips[1:])
    seen = {build_narrative(NarrativeType.QUIET, NarrativeContext(personality="laozhang", exclude=other))["text"] for _ in range(30)}
    assert one in seen or len(snips) == 1
