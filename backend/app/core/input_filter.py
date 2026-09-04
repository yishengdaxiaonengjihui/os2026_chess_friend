"""输入过滤（问题3）★

用户语音/文字输入的智能过滤：
1. 噪音判定：过短、纯标点/表情/语气词等无信息量输入直接忽略
   （不打断数字人、不入记忆、不触发响应）。
2. 连续消息只响应最新：短时间内连续发多条消息（语音误触发/连击），
   只保留最新一条作为响应上下文，避免 AI 被无关旧消息干扰。

用法：每会话持有一个 InputFilter 实例，收到输入时调用 check()：
    verdict = filter.check(text)
    - "noise"  -> 忽略（噪音）
    - "dedup"  -> 连续消息，仅最新生效（应覆盖记忆中的上一条用户输入）
    - "ok"     -> 正常响应
"""
from __future__ import annotations

import re
import time

# 去抖窗口：距上次有效输入短于此秒数视为「连续消息」
DEBOUNCE_SECONDS = 2.5
# 最小有效长度（去空白后）
MIN_LEN = 1
# 纯无意义字符：标点/符号/数字/表情（emoji）等
_NOISE_ONLY = re.compile(r"^[\s\d\W_]+$", re.UNICODE)
# 常见语气词/无意义拟声（中文、英文、表情文本）
_NOISE_WORDS = {
    "嗯", "哦", "啊", "诶", "唉", "喂", "哈", "嘿", "唔", "呃", "恩",
    "嗯嗯", "哦哦", "啊啊", "哈哈", "呵呵", "嘿嘿", "好的", "好", "ok",
    "okay", "hello", "hi", "在吗", "在不在", "嗯哼", "嘿嘿嘿", "哈哈哈",
}


def is_noise(text: str) -> bool:
    """判定输入是否为噪音：过短 / 纯标点表情 / 无意义语气词。"""
    if not text:
        return True
    t = text.strip()
    if len(t) <= MIN_LEN:
        return True
    # 纯标点 / 符号 / emoji
    if _NOISE_ONLY.match(t):
        return True
    # 纯语气词（可能带少量重复标点）
    core = t.rstrip("！!？?。.,，~～ ")
    if core in _NOISE_WORDS:
        return True
    # 单一字符大量重复（如 "啊啊啊啊"）
    if len(t) >= 3 and len(set(t)) == 1:
        return True
    return False


class InputFilter:
    """每会话输入过滤器：维护去抖状态，返回响应判定。"""

    def __init__(self) -> None:
        self._last_ts: float = 0.0
        self._last_text: str = ""

    def check(self, text: str, now: float | None = None) -> str:
        """判定输入：返回 "noise" / "dedup" / "ok"。"""
        if is_noise(text):
            return "noise"
        now = time.time() if now is None else now
        within_window = (now - self._last_ts) < DEBOUNCE_SECONDS
        # 上次有效输入仍在窗口内且内容不同 -> 连续消息，仅响应最新
        if within_window and self._last_text and self._last_text != text:
            self._last_ts = now
            self._last_text = text
            return "dedup"
        self._last_ts = now
        self._last_text = text
        return "ok"
