"""模型管理（通用设置-模型管理）。

可用模型清单 + 运行时切换（内存态，重启恢复配置默认）。
切换后 LLMClient 会优先使用该模型，失败自动回退配置默认模型。
"""
from __future__ import annotations

AVAILABLE_MODELS: list[dict] = [
    {"id": "doubao-seed-2.0-mini", "label": "豆包 Seed 2.0 Mini（默认·快）"},
    {"id": "doubao-seed-1.6-flash", "label": "豆包 Seed 1.6 Flash（快）"},
    {"id": "doubao-1.5-pro-32k-250115", "label": "豆包 1.5 Pro 32K（强）"},
    {"id": "deepseek-v3", "label": "DeepSeek V3（通用）"},
]

_runtime_model: str | None = None  # 运行时覆盖；None = 用配置默认


def list_models(default: str = "") -> list[dict]:
    effective = _runtime_model or default
    return [dict(m, current=(m["id"] == effective)) for m in AVAILABLE_MODELS]


def set_runtime_model(model_id: str) -> None:
    global _runtime_model
    if model_id not in {m["id"] for m in AVAILABLE_MODELS}:
        raise ValueError(f"未知模型: {model_id}")
    _runtime_model = model_id


def get_runtime_model() -> str | None:
    return _runtime_model


def effective_model(default: str) -> str:
    return _runtime_model or default
