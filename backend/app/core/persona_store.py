"""轻量人格仓库（问题6）★

人格设定外置为 personas.json（梗概常驻 + 外置故事 JSON）：
- synopsis：人格梗概，常驻系统角色 —— 决定棋友说话的语气与身份。
- story：外置故事（棋友的背景往事），非空时注入 prompt 作为「你记得的往事」。
- stories：短回忆片段列表（1~2 句/条），供主动叙事（narrative_driver）随机挑一条讲。
- hooks：触发钩子（占位，如特定棋局事件时注入对应故事片段）。

好处：人格即数据，改 JSON 不用改代码；故事可外扩不膨胀 prompt。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_PERSONAS_FILE = Path(__file__).parent / "personas.json"
DEFAULT_PERSONALITY = "laozhang"


@lru_cache(maxsize=1)
def load_personas() -> dict[str, Any]:
    """读取 personas.json；文件缺失/损坏时回退内置默认。"""
    default = {
        "laozhang": {
            "synopsis": "你是「老张」——一位住在社区棋摊旁的退休象棋老手，性格爽朗、爱下棋也爱唠嗑，"
                        "现在作为独居老人李大爷的专属数字人象棋棋友陪他下棋。"
                        "你既是合格的棋手，也是能给棋友带来陪伴感的老朋友。",
            "story": "",
            "stories": [],
            "hooks": [],
        },
        "xiaoya": {
            "synopsis": "你是「小雅」——一位温柔耐心的年轻象棋陪练老师，说话轻声细语、循循善诱，"
                        "现在作为独居老人李大爷的专属数字人象棋陪练陪他下棋。"
                        "你认真对待每一步棋，多用鼓励的语气，帮棋友放松心态。",
            "story": "",
            "stories": [],
            "hooks": [],
        },
    }
    try:
        data = json.loads(_PERSONAS_FILE.read_text(encoding="utf-8"))
        personas = data.get("personas") or {}
        # 与内置并集，保证至少有两个基础人格
        merged = {**default, **personas}
        for pid in merged:
            p = merged[pid] or {}
            merged[pid] = {
                "synopsis": p.get("synopsis") or default.get(pid, {}).get("synopsis", ""),
                "story": p.get("story") or "",
                "stories": p.get("stories") or [],
                "storylines": p.get("storylines") or [],
                "hooks": p.get("hooks") or [],
            }
        return merged
    except Exception:  # noqa: BLE001 文件缺失/解析失败 -> 内置兜底
        return default


def persona_for(personality: str) -> dict[str, Any]:
    """按人格取轻量设定；未知人格回退默认（老张）。"""
    personas = load_personas()
    return personas.get(personality) or personas[DEFAULT_PERSONALITY]


def list_personas() -> list[str]:
    return list(load_personas().keys())


def synopsis(personality: str) -> str:
    """梗概（常驻）。"""
    return persona_for(personality)["synopsis"]


def story(personality: str) -> str:
    """外置背景往事（非空时才注入 prompt）。"""
    return persona_for(personality)["story"]


def stories(personality: str) -> list[str]:
    """短回忆片段列表（碎片兜底：无 storylines 时供主动叙事随机挑一条讲）。"""
    return persona_for(personality).get("stories") or []


def storylines(personality: str) -> list[dict]:
    """章节式故事线（4 段主线：源头→发展→高潮→收尾），供主动叙事按顺序连续讲。

    每条结构：{id, name, tags: [关键词], segments: [段文本, ...]}。
    事件关键词命中 tags/段文本时，从该故事线源头（第 0 段）开始讲。
    """
    return persona_for(personality).get("storylines") or []


def story_prompt_block(personality: str) -> str:
    """故事注入块：有故事时返回「你记得的往事」段落，否则空串。"""
    s = story(personality).strip()
    if not s:
        return ""
    return f"\n\n【你记得的往事】\n{s}"
