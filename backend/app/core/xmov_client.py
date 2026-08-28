"""魔珐星云 XmovAvatar 协议适配层（自研核心，第三阶段）★

架构认知：星云 XmovAvatar 是「浏览器端 Web SDK」（litesdk），由前端负责
3D 渲染 / 口型 / 语音，后端并不直连星云。本模块在后端承担两件事：

1. 协议适配（纯函数）：
   - 中文情绪标签 -> SDK emotion 枚举（happy/sad/angry/surprised/neutral）
   - 中文动作标签 -> KA 关键动作（SSML <ue4event>）
   - 组装 SDK speak() 需要的 SSML 文本
2. 表演时序调度（XmovAvatarClient）：
   - 估算一段台词的播放时长，向对局 WS 广播 speaking/idle 状态
   - 供前端数字人状态指示（即使未加载 3D SDK 也能看到"讲话中/就绪"）

真实渲染链路：后端 WS 把「SSML+emotion」推给前端，前端调
  avatar.speak(ssml, isStart, isEnd, { emotion })
即可驱动数字人。密钥/形象/音色配置在 .env。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ---- 情绪映射：本项目中文情绪标签 -> 星云 SDK emotion 枚举 ----
EMOTION_MAP: dict[str, str] = {
    "平静": "neutral",
    "喜悦": "happy",
    "赞赏": "happy",
    "鼓励": "happy",
    "得意": "happy",
    "惋惜": "sad",
    "惊讶": "surprised",
    "沉思": "neutral",
    "认真": "neutral",
    "严肃": "angry",
}
DEFAULT_EMOTION = "neutral"

# ---- 动作映射：动作标签 -> KA 关键动作 / 动作意图 ----
# 说明：KA 与表情同属「定制化角色功能」，不同形象支持的动作清单不同
# （工作台可查）。列表依据官方文档示例动作（wave_hand/bow/Elevate/KeyPoints/
# Pointscreen），其余用 ka_intent 意图让后端编排实际 KA；不支持的会被服务端忽略。
ACTION_SEMANTIC_MAP: dict[str, str] = {
    "idle": "",        # 无动作
    "nod": "Agreement",     # 点头/赞同
    "smile": "Happy",       # 微笑
    "frown": "Worried",     # 皱眉
    "applaud": "Applaud",   # 鼓掌
    "lean": "Listen",       # 侧身倾听
    "wave": "wave_hand",    # 挥手（文档示例动作）
    "bow": "bow",           # 鞠躬（文档示例动作）
    "shrug": "Shrug",       # 耸肩
}
# 已确认的「ka」动作（其余走 ka_intent 意图）
_KA_DIRECT = {"wave_hand", "bow"}


def emotion_to_sdk(tag: str) -> str:
    """中文情绪标签 -> SDK emotion 枚举。"""
    return EMOTION_MAP.get(tag, DEFAULT_EMOTION)


def action_to_semantic(tag: str) -> str:
    """中文动作标签 -> KA 动作/意图名（空串表示无动作）。"""
    return ACTION_SEMANTIC_MAP.get(tag, "")


def build_ssml(text: str, action_tag: str = "idle") -> str:
    """组装 SDK speak() 所需的 SSML 文本（含关键动作标签）。"""
    escaped = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    semantic = action_to_semantic(action_tag)
    if not semantic or action_tag == "idle":
        return f"<speak>{escaped}</speak>"
    if semantic in _KA_DIRECT:
        inner = f"<action_semantic>{semantic}</action_semantic>"
    else:
        inner = f"<ka_intent>{semantic}</ka_intent>"
    return (
        f"<speak><ue4event><type>{'ka' if semantic in _KA_DIRECT else 'ka_intent'}</type>"
        f"<data>{inner}</data></ue4event>{escaped}</speak>"
    )


def estimate_seconds(text: str) -> float:
    """按字数估算 TTS 播放时长（用于后端状态时序，前端仍以 SDK 回调为准）。"""
    if not text:
        return 0.6
    return max(0.6, min(3.0, len(text) * 0.12))


class XmovAvatarClient:
    """表演时序调度器（后端侧）。

    说明：3D 渲染由浏览器端 SDK 完成，本类只负责在服务端估算播放时长、
    广播 speaking/idle 状态，保证前端数字人指示与真实 SDK 联动一致。
    """

    def __init__(self, app_id: str = "", app_secret: str = "", ws_url: str = "") -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.ws_url = ws_url
        self._connected = False
        self._session_id: Optional[str] = None
        self._speaking = False
        self.on_state: Optional[Callable[[str], None]] = None  # "speaking"/"idle"

    @property
    def available(self) -> bool:
        """后端调度器始终可用（真实 3D 渲染在浏览器端）。"""
        return self._connected

    @property
    def speaking(self) -> bool:
        return self._speaking

    def _notify_state(self, state: str) -> None:
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:  # noqa: BLE001
                logger.exception("on_state 回调异常")

    async def connect(self) -> None:
        """建立会话上下文。后端不直连星云：SDK 鉴权/渲染均在浏览器端。"""
        self._session_id = f"ses-{int(time.time() * 1000)}"
        self._connected = True
        if self.app_id and self.app_secret:
            logger.info("[xmov] 已配置星云密钥，浏览器端 XmovAvatar 将使用 appId=%s 渲染", self.app_id[:6])
        else:
            logger.info("[xmov] 未配置星云密钥，前端将走本地朗读/文字降级")

    async def close(self) -> None:
        self._connected = False
        self._speaking = False
        self._notify_state("idle")

    async def speak(self, text: str, emotion: str = "平静", action: str = "idle") -> None:
        """按台词长度模拟播放时序，期间状态为 speaking。"""
        if not self._connected:
            return
        ssml = build_ssml(text, action)
        logger.info("[xmov] 表演: emotion=%s action=%s ssml=%s", emotion_to_sdk(emotion), action_to_semantic(action), ssml)
        self._speaking = True
        self._notify_state("speaking")
        await asyncio.sleep(estimate_seconds(text))
        self._speaking = False
        self._notify_state("idle")

    def stop_speaking(self) -> None:
        """语音打断（barge-in）：立即终止当前表演。"""
        self._speaking = False
        self._notify_state("idle")
