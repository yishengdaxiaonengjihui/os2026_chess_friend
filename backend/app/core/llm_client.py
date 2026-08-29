"""LLM 客户端（自研核心 4/5）★

调用大模型（OpenAI 兼容协议），强约束输出 JSON {speech_text, emotion_tag, action_tag}。
未配置 API Key 时进入 mock 模式，保证演示/测试无需真实密钥也能跑通链路。
"""
from __future__ import annotations

import json
import random
import re
from typing import Any, Optional

from ..config import get_settings
from .model_registry import effective_model

MOCK_LINES = [
    "好棋好棋，这一步走得挺稳当的！",
    "哟，这步有点意思，我得想想。",
    "哈哈，被我吃了个子吧，别急，再来。",
    "行啊老哥，最近棋力见长！",
    "这盘下得胶着，咱慢慢来。",
]


class LLMOutputError(ValueError):
    """LLM 输出无法解析为合法结构。"""


def _parse_llm_json(text: str) -> dict[str, Any]:
    """容忍 model 输出前后有多余文字/代码块，尽力提取 JSON。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", text, flags=re.S)
        if not m:
            raise LLMOutputError(f"无法从模型输出解析 JSON: {text[:120]!r}")
        obj = json.loads(m.group(0))
    return obj


def _validate(obj: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化 LLM 输出结构。"""
    speech = str(obj.get("speech_text", "")).strip()
    if not speech:
        raise LLMOutputError("模型输出缺少 speech_text")
    emotion = str(obj.get("emotion_tag", "平静"))
    action = str(obj.get("action_tag", "idle"))
    return {"speech_text": speech, "emotion_tag": emotion, "action_tag": action}


def _mock_reply(messages: list[dict]) -> dict[str, Any]:
    last_user = ""
    for m in reversed(messages):
        if m["role"] == "user":
            last_user = m["content"]
            break
    ctx = messages[0]["content"] if messages else ""
    # 从棋局上下文里挑一个情绪关键词，让 mock 也稍微贴合局面
    emotion = "平静"
    if "吃" in (ctx + last_user):
        emotion = "得意" if "应了" in ctx else "惋惜"
    elif "将军" in ctx:
        emotion = "惊讶"
    return {
        "speech_text": random.choice(MOCK_LINES),
        "emotion_tag": emotion,
        "action_tag": random.choice(["nod", "smile", "lean"]),
    }


class LLMClient:
    """OpenAI 兼容聊天客户端，带 JSON 强约束 + 重试 + mock 降级。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        if self.settings.llm_configured:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self.settings.llm_api_key,
                    base_url=self.settings.llm_base_url,
                )
            except Exception:
                self._client = None

    @property
    def mock_mode(self) -> bool:
        return self._client is None

    def chat(self, messages: list[dict], max_retries: int = 2) -> dict[str, Any]:
        if self._client is None:
            return _mock_reply(messages)

        default_model = self.settings.llm_model
        # 模型顺序：运行时选择模型 -> 配置默认模型（运行时模型失败时回退）
        models = [effective_model(default_model)]
        if models[0] != default_model:
            models.append(default_model)

        last_err: Optional[Exception] = None
        for model in models:
            for _ in range(max_retries + 1):
                try:
                    kwargs: dict[str, Any] = {
                        "model": model,
                        "messages": messages,
                        "max_tokens": self.settings.llm_max_tokens,
                        "temperature": self.settings.llm_temperature,
                        "response_format": {"type": "json_object"},
                    }
                    if self.settings.llm_thinking_off:
                        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
                    resp = self._client.chat.completions.create(**kwargs)
                    raw = resp.choices[0].message.content or ""
                    obj = _validate(_parse_llm_json(raw))
                    return obj
                except Exception as e:  # 网络/解析/限流都重试
                    last_err = e
        # 全部重试失败：mock 兜底，保证服务不挂
        return _mock_reply(messages)
