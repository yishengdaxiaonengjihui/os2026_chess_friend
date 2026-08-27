"""具身指令分发器（自研核心 5/5）★

对齐 spec 2.1「具身指令分发器」：参考 voxavatar 状态机思路自研。
维护状态机 IDLE / THINKING / SPEAKING；管理表演队列、用户打断（barge-in）逻辑；
调用魔珐星云 SDK 接口。ENABLE_DIGITAL_HUMAN=false 时整体降级为 no-op，保留业务逻辑。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)


class AvatarState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass
class PerformanceCommand:
    """一条具身指令：台词 + 情绪 + 动作（后续映射为魔珐星云 SDK 调用）。"""
    speech_text: str
    emotion_tag: str = "平静"
    action_tag: str = "idle"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "speech_text": self.speech_text,
            "emotion_tag": self.emotion_tag,
            "action_tag": self.action_tag,
        }


class AvatarDispatcher:
    """表演队列 + 状态机 + 打断控制。

    当前为无头实现：不真实连接魔珐星云 SDK，而是输出标准指令流（供 WebSocket 推送），
    并预留 `_xmov_client` 挂接点，第三阶段接入真实 SDK。
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.state = AvatarState.IDLE
        self._queue: list[PerformanceCommand] = []
        self._interrupted = False
        self._xmov_client: Optional[Any] = None  # 第三阶段挂接魔珐星云 SDK

    @property
    def enabled(self) -> bool:
        return self.settings.enable_digital_human

    def enqueue(self, command: PerformanceCommand) -> None:
        """入队一条具身指令。数字人关闭时直接丢弃（业务逻辑不受影响）。"""
        if not self.enabled:
            logger.info("[avatar] 数字人已降级，忽略指令: %s", command.speech_text)
            return
        self._queue.append(command)
        self.state = AvatarState.THINKING

    def interrupt(self) -> None:
        """用户语音打断：终止当前语音动画，清空表演队列。"""
        self._interrupted = True
        self._queue.clear()
        self.state = AvatarState.IDLE
        if self._xmov_client is not None:
            # 真实 SDK 的 cancel/stop 调用点
            self._xmov_client.stop_speaking()

    def pop_next(self) -> Optional[PerformanceCommand]:
        """取出一条待表演指令（模拟演出推进）。"""
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

    def reset(self) -> None:
        self._queue.clear()
        self._interrupted = False
        self.state = AvatarState.IDLE

    async def play(self, command: PerformanceCommand) -> Optional[dict[str, Any]]:
        """异步演出一条指令：入队→模拟播放→返回指令（供 WebSocket 下发）。"""
        if not self.enabled:
            return None
        self.enqueue(command)
        # 模拟播放耗时（口型/动画时长），真实实现改为等待 SDK 完成回调
        await asyncio.sleep(0.05)
        return self.pop_next().to_dict() if self._queue else command.to_dict()

    def play_sync(self, command: PerformanceCommand) -> Optional[dict[str, Any]]:
        """同步演出一条指令：入队并立即返回指令内容（供 REST 同步链路使用）。"""
        if not self.enabled:
            return None
        self.enqueue(command)
        return command.to_dict()
