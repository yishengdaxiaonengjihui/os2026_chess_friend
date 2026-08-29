"""具身指令分发器（自研核心 5/5）★

对齐 spec 2.1「具身指令分发器」：参考 voxavatar 状态机思路自研。
维护状态机 IDLE / THINKING / SPEAKING；管理表演队列、用户打断（barge-in）；
第三阶段接入魔珐星云 XmovAvatar 客户端（未配置密钥时 simulation 模式）。
ENABLE_DIGITAL_HUMAN=false 时整体降级为 no-op，保留业务逻辑。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from ..config import get_settings
from . import ws_hub
from .xmov_client import XmovAvatarClient, action_to_semantic, build_ssml, emotion_to_sdk

logger = logging.getLogger(__name__)


class AvatarState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass
class PerformanceCommand:
    """一条具身指令：台词 + 情绪 + 动作（映射为魔珐星云 SDK 调用）。"""
    speech_text: str
    emotion_tag: str = "平静"
    action_tag: str = "idle"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """转成 SDK-ready 指令：含情绪枚举、关键动作、SSML（供前端 avatar.speak）。"""
        return {
            "speech_text": self.speech_text,
            "emotion_tag": self.emotion_tag,
            "action_tag": self.action_tag,
            "emotion_sdk": emotion_to_sdk(self.emotion_tag),
            "action_semantic": action_to_semantic(self.action_tag),
            "ssml": build_ssml(self.speech_text, self.action_tag),
        }


class AvatarDispatcher:
    """表演队列 + 状态机 + 打断控制 + 星云数字人驱动。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.state = AvatarState.IDLE
        self._queue: list[PerformanceCommand] = []
        self._interrupted = False
        self._driving = False
        self._broadcaster: Optional[Callable[[str, Optional[dict]], None]] = None
        # 第三阶段：真实 XmovAvatar 客户端（无密钥时自动 simulation）
        self._xmov = XmovAvatarClient(
            app_id=self.settings.xmov_app_id,
            app_secret=self.settings.xmov_app_secret,
            ws_url=self.settings.xmov_ws_url,
        )

    # ---- 配置 ----
    @property
    def enabled(self) -> bool:
        return self.settings.enable_digital_human

    def set_broadcaster(self, fn: Callable[[str, Optional[dict]], None]) -> None:
        """注入状态广播回调（由编排层绑定到 ws_hub）。"""
        self._broadcaster = fn

    def _emit(self, state: str, command: Optional[dict] = None) -> None:
        if self._broadcaster:
            try:
                self._broadcaster(state, command)
            except Exception:  # noqa: BLE001
                logger.exception("广播回调异常")

    # ---- 队列控制 ----
    def enqueue(self, command: PerformanceCommand) -> None:
        if not self.enabled:
            logger.info("[avatar] 数字人已降级，忽略指令: %s", command.speech_text)
            return
        self._queue.append(command)
        self.state = AvatarState.THINKING
        self._emit("thinking")

    def pop_next(self) -> Optional[PerformanceCommand]:
        if self._interrupted:
            self._interrupted = False
            return None
        if not self._queue:
            self.state = AvatarState.IDLE
            return None
        cmd = self._queue.pop(0)
        self.state = AvatarState.SPEAKING
        return cmd

    def peek(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._queue]

    def interrupt(self) -> None:
        """用户语音打断：终止当前语音动画，清空表演队列。"""
        self._interrupted = True
        self._queue.clear()
        self.state = AvatarState.IDLE
        self._xmov.stop_speaking()
        self._emit("idle")

    def reset(self) -> None:
        self._queue.clear()
        self._interrupted = False
        self.state = AvatarState.IDLE

    def think_only(self) -> None:
        """静默思索（问题1）：只广播 thinking 状态，不入队语音。"""
        if not self.enabled:
            return
        self.state = AvatarState.THINKING
        self._emit("thinking")

    # ---- 驱动 ----
    def _schedule_drive(self) -> None:
        """在运行中的事件循环上调度后台驱动（尽力而为）。"""
        loop = ws_hub.get_loop()
        if loop is None or loop.is_closed() or self._driving:
            return
        self._driving = True
        try:
            asyncio.run_coroutine_threadsafe(self._drive(loop), loop)
        except Exception:  # noqa: BLE001
            logger.exception("调度数字人驱动失败")
            self._driving = False

    async def _drive(self, loop: asyncio.AbstractEventLoop) -> None:
        """顺序消费表演队列，驱动星云客户端播放，广播 speaking/idle。"""
        try:
            await self._xmov.connect()
            while not self._interrupted:
                cmd = self.pop_next()
                if cmd is None:
                    break
                self._emit("speaking", cmd.to_dict())
                await self._xmov.speak(cmd.speech_text, cmd.emotion_tag, cmd.action_tag)
                self._emit("idle")
        except Exception:  # noqa: BLE001
            logger.exception("数字人驱动异常（不影响主流程）")
            self._emit("idle")
        finally:
            self._driving = False

    async def play(self, command: PerformanceCommand) -> Optional[dict[str, Any]]:
        """异步演出一条指令：入队并等待完成，返回指令内容。"""
        if not self.enabled:
            return None
        self.enqueue(command)
        self._schedule_drive()
        return command.to_dict()

    def play_sync(self, command: PerformanceCommand) -> Optional[dict[str, Any]]:
        """同步演出一条指令：入队并立即返回指令内容（供 REST 同步链路使用）。"""
        if not self.enabled:
            return None
        self.enqueue(command)
        self._schedule_drive()
        return command.to_dict()
