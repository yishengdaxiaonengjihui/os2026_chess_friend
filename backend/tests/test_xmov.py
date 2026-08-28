"""第三阶段：星云协议适配层(映射/SSML) + 表演时序调度 + 分发器状态机测试。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.avatar_dispatcher import AvatarDispatcher, AvatarState, PerformanceCommand
from backend.app.core.xmov_client import (
    XmovAvatarClient,
    action_to_semantic,
    build_ssml,
    emotion_to_sdk,
    estimate_seconds,
)


# ---- 协议适配层 ----
def test_emotion_mapping():
    assert emotion_to_sdk("喜悦") == "happy"
    assert emotion_to_sdk("赞赏") == "happy"
    assert emotion_to_sdk("惋惜") == "sad"
    assert emotion_to_sdk("惊讶") == "surprised"
    assert emotion_to_sdk("平静") == "neutral"
    assert emotion_to_sdk("不存在的情绪") == "neutral"  # 默认


def test_action_mapping():
    assert action_to_semantic("wave") == "wave_hand"
    assert action_to_semantic("bow") == "bow"
    assert action_to_semantic("applaud") == "Applaud"
    assert action_to_semantic("idle") == ""
    assert action_to_semantic("未知动作") == ""


def test_build_ssml():
    # 无动作：纯文本 SSML
    assert build_ssml("你好", "idle") == "<speak>你好</speak>"
    # 已知 ka 动作：wave_hand
    assert "<action_semantic>wave_hand</action_semantic>" in build_ssml("再见", "wave")
    # 未知 ka 意图：ka_intent
    assert "<ka_intent>Applaud</ka_intent>" in build_ssml("太棒了", "applaud")
    # XML 转义
    assert "&amp;" in build_ssml("3 < 5 & 6", "idle")


# ---- 时序调度器（后端只调度，不直连星云）----
def test_xmov_timeline_simulation():
    client = XmovAvatarClient(app_id="", app_secret="", ws_url="")
    asyncio.run(client.connect())
    assert client.available is True  # 后端调度器始终可用
    states: list[str] = []
    client.on_state = lambda s: states.append(s)
    asyncio.run(client.speak("你好呀老哥", "喜悦", "nod"))
    assert states == ["speaking", "idle"]
    assert client.speaking is False
    assert estimate_seconds("你好") >= 0.6


def test_xmov_with_creds_still_schedules():
    """即使配置了真实密钥，后端也只做时序调度（3D 渲染在浏览器端 SDK）。"""
    client = XmovAvatarClient(app_id="abc123", app_secret="secret", ws_url="https://nebula-agent.xingyun3d.com")
    asyncio.run(client.connect())
    states: list[str] = []
    client.on_state = lambda s: states.append(s)
    asyncio.run(client.speak("这一步走得漂亮！", "赞赏", "applaud"))
    assert states[0] == "speaking" and states[-1] == "idle"
    client.stop_speaking()
    assert client.speaking is False


# ---- 分发器状态机 ----
def test_dispatcher_state_machine():
    d = AvatarDispatcher()
    assert d.enabled is True
    cmd = PerformanceCommand(speech_text="你走得好！", emotion_tag="赞赏", action_tag="applaud")
    out = d.play_sync(cmd)
    assert out["speech_text"] == "你走得好！"
    assert out["emotion_sdk"] == "happy"          # SDK-ready
    assert "<ka_intent>Applaud</ka_intent>" in out["ssml"]
    assert d.state == AvatarState.THINKING
    assert len(d.peek()) == 1

    d.interrupt()
    assert d.state == AvatarState.IDLE
    assert d.peek() == []
    assert d.pop_next() is None


def test_dispatcher_disabled_is_noop():
    d = AvatarDispatcher()
    d.settings.enable_digital_human = False
    out = d.play_sync(PerformanceCommand(speech_text="你好"))
    assert out is None
    assert d.peek() == []
