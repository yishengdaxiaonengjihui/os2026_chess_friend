"""问题4+问题13：主动叙事节拍器 —— 决策器 + 章节式故事线顺序推进 + 事件源头。"""
import pytest

from backend.app.core.narrative_driver import (
    NarrativeContext,
    NarrativeType,
    build_narrative,
    narrate,
)
from backend.app.core.persona_store import storylines as persona_storylines


def _all_segment_texts(personality: str) -> list[str]:
    texts = []
    for line in persona_storylines(personality):
        texts.extend(line.get("segments") or [])
    return texts


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


def test_quiet_uses_storyline_source_first():
    """静默时优先讲故事线，且无进度时从源头（第 0 段）开始。"""
    for personality in ("laozhang", "xiaoya"):
        d = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality, move_index=10, quiet_seconds=99.0))
        assert isinstance(d, dict) and d["text"]
        assert d["seg_idx"] == 0, "无进度时应从源头（第 0 段）开始讲"
        assert d["text"] in _all_segment_texts(personality)
        assert d["emotion_tag"] in ("沉思", "平静", "得意")
        assert d["action_tag"] in ("idle", "nod", "smile")


def test_storyline_advances_in_order():
    """故事线按顺序推进：源头->发展->高潮->收尾；讲完换新故事回到源头。"""
    personality = "laozhang"
    lines = persona_storylines(personality)
    seg_count = len(lines[0]["segments"])
    prog = None
    played = []
    for _ in range(seg_count):
        ctx = NarrativeContext(personality=personality, move_index=10, quiet_seconds=99.0, story_progress=prog)
        d = build_narrative(NarrativeType.QUIET, ctx)
        played.append((d["seg_idx"], d["done"]))
        assert d["text"] in _all_segment_texts(personality)
        if d.get("story_id") and not d["done"]:
            prog = {"story_id": d["story_id"], "seg_idx": d["seg_idx"] + 1}
        elif d.get("done"):
            prog = None
    # 0..N-1 顺序推进，最后一段 done=True
    assert [p[0] for p in played] == list(range(seg_count))
    assert played[-1][1] is True
    # 讲完 -> 换新故事从源头开始
    d2 = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality, move_index=10, quiet_seconds=99.0))
    assert d2["seg_idx"] == 0


def test_event_hit_starts_from_source_when_not_telling():
    """事件命中且没在讲这条线 -> 从该线源头（第 0 段）讲（先抛源头）。"""
    d = build_narrative(
        NarrativeType.QUIET,
        NarrativeContext(
            personality="laozhang", move_index=10, quiet_seconds=99.0,
            events=["玩家吃子：吃掉对方炮"], story_progress={"story_id": "other-line", "seg_idx": 1},
        ),
    )
    assert d["seg_idx"] == 0
    assert d["text"] == persona_storylines("laozhang")[0]["segments"][0]
    assert d["story_id"] == "wuzi-qi"


def test_event_hit_continues_current_line():
    """事件命中但正在讲这条线 -> 继续当前进度段（连续性优先，不因事件重讲）。"""
    d = build_narrative(
        NarrativeType.QUIET,
        NarrativeContext(
            personality="laozhang", move_index=10, quiet_seconds=99.0,
            events=["玩家吃子：吃掉对方炮"], story_progress={"story_id": "wuzi-qi", "seg_idx": 2},
        ),
    )
    assert d["seg_idx"] == 2
    assert d["text"] == persona_storylines("laozhang")[0]["segments"][2]
    assert d["story_id"] == "wuzi-qi"


def test_recently_told_dedup_window():
    """最近已讲窗口去重：选中的段若刚讲过，换同线后续段，避免同一句紧挨着重讲。"""
    # 无进度 -> 源头段；把源头段放入已讲窗口 -> 应换到第 1 段
    d = build_narrative(
        NarrativeType.QUIET,
        NarrativeContext(
            personality="laozhang", move_index=10, quiet_seconds=99.0,
            story_progress={"story_id": "wuzi-qi", "seg_idx": 0},
            exclude=[persona_storylines("laozhang")[0]["segments"][0]],
        ),
    )
    assert d["seg_idx"] == 1, "源头段刚讲过应换到下一段"
    assert d["text"] == persona_storylines("laozhang")[0]["segments"][1]


def test_quiet_fallback_without_storylines(monkeypatch):
    """没有 storylines 时回退碎片 stories / 语气词库，不崩。"""
    from backend.app.core import narrative_driver as nd

    monkeypatch.setattr(nd, "persona_storylines", lambda p: [])
    monkeypatch.setattr(nd, "persona_stories", lambda p: ["嗯，想起个事儿。"])
    for personality in ("laozhang", "xiaoya", "unknown"):
        d = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality, move_index=10, quiet_seconds=99.0))
        assert isinstance(d, dict) and d["text"]
        assert d["story_id"] is None


def test_build_narrative_per_personality():
    """按人格取故事线；未知人格回退老张。"""
    for personality in ("laozhang", "xiaoya", "unknown"):
        d = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=personality, move_index=10, quiet_seconds=99.0))
        assert isinstance(d, dict) and d["text"]
