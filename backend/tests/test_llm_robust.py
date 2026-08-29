"""问题10：LLM 输出异常兜底 —— JSON 解析失败/返回异常时使用安全台词+中性情绪+默认动作，绝不抛错。"""
import pytest

from backend.app.core.llm_client import (
    LLMClient,
    LLMOutputError,
    SAFE_FALLBACK_TEXT,
    _parse_llm_json,
    _safe_fallback_reply,
)


class _BoomCompletions:
    @staticmethod
    def create(**kwargs):
        raise RuntimeError("网络故障")


class _BoomChat:
    completions = _BoomCompletions()


class _BoomClient:
    chat = _BoomChat()


def test_parse_llm_json_tolerates_markdown_fence():
    raw = '\n\`\`\`json\n{"speech_text": "好棋", "emotion_tag": "平静"}\n\`\`\`\n'
    obj = _parse_llm_json(raw)
    assert obj["speech_text"] == "好棋"


def test_parse_llm_json_extracts_embedded_json():
    obj = _parse_llm_json('前面有废话 {"speech_text": "下得好"} 后面也有')
    assert obj["speech_text"] == "下得好"


def test_parse_llm_json_raises_on_garbage():
    with pytest.raises(LLMOutputError):
        _parse_llm_json("完全不是JSON，也没有大括号")


def test_safe_fallback_is_neutral_and_complete():
    fb = _safe_fallback_reply()
    assert fb["speech_text"] == SAFE_FALLBACK_TEXT
    assert fb["speech_text"].strip()
    assert fb["emotion_tag"] == "平静"
    assert fb["action_tag"] in ("nod", "idle", "think")


def test_chat_never_raises_and_returns_safe_fallback_on_llm_failure():
    llm = LLMClient()
    llm._client = _BoomClient()  # 让真实调用路径必然抛异常
    out = llm.chat([{"role": "user", "content": "落子后说说"}], max_retries=0)
    assert out["speech_text"].strip()
    assert out["emotion_tag"] == "平静"
    assert "action_tag" in out


def test_chat_mock_mode_still_valid_when_no_client():
    llm = LLMClient()
    llm._client = None
    out = llm.chat([{"role": "user", "content": "测试"}])
    assert out["speech_text"].strip()
    assert "emotion_tag" in out and "action_tag" in out
