"""术语净化过滤器（自研，问题5 第四层兜底）★

四层术语净化体系的最后一层：系统 Prompt 已禁止、语境已口语化，
这里再用正则兜底过滤 LLM 输出中的机械棋谱话术（坐标 / 专业记谱），
保证送进 TTS 的台词彻底老人化口语。
"""
from __future__ import annotations

import re

# 棋盘坐标：a0..i9（中国象棋引擎 square 记法）
_COORD = r"[a-i][0-9]"
# 中文专业记谱：如 炮二平五 / 马三进四 / 车一退二
_CH_NOTATION = r"[炮车马相仕帅兵卒将士象][一二三四五六七八九][进退平][一二三四五六七八九]"

# 按序替换：先整句坐标移动，再中文记谱，最后清理裸坐标
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 整句坐标移动：从a6走到a5 / 从a2进到b4 / a3进b5
    (re.compile(rf"从{_COORD}(?:走|进|退|平)?(?:到|至){_COORD}"), "走了一步"),
    (re.compile(rf"{_COORD}(?:走|进|退|平)?(?:到|至){_COORD}"), "走了一步"),
    (re.compile(rf"{_COORD}(?:走|进|退|平){_COORD}"), "走了一步"),
    (re.compile(rf"{_COORD}[→\-]>{_COORD}|{_COORD}[→\-]{_COORD}"), "那一步"),
    (re.compile(_CH_NOTATION), "那一步"),
    (re.compile(_COORD), ""),
    (re.compile(r"\bFEN\b\s*[=：:]?\s*\S*", re.IGNORECASE), ""),
]


def sanitize_speech(text: str) -> str:
    """把台词里的坐标 / 记谱 / 机械描述替换为通俗口语；无则原样返回。"""
    if not text:
        return text
    out = text
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    # 清理多余空白与重复标点
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"[，,。．.]{2,}", "，", out)
    out = out.strip(" ，,")
    return out
