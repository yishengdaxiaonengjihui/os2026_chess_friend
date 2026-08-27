"""Pydantic 数据模型（API 层请求/响应契约）。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class NewGameRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    personality: str = Field("laozhang", description="人格：laozhang / xiaoya")


class NewGameResponse(BaseModel):
    game_id: str
    user_id: str
    fen: str
    side: str
    digital_human_enabled: bool


class MoveRequest(BaseModel):
    game_id: str
    user_id: str
    fen: str
    from_sq: str
    to_sq: str
    thinking_text: Optional[str] = None


class LLMOutput(BaseModel):
    speech_text: str
    emotion_tag: str
    action_tag: str


class MoveResponse(BaseModel):
    game_id: str
    ai_move: dict[str, Any]
    new_fen: str
    events: list[str]
    llm_output: LLMOutput
    avatar_command: Optional[dict[str, Any]] = None
    long_term_memories: list[str]
    profile: dict[str, Any]


class ProfileResponse(BaseModel):
    user_id: str
    profile: dict[str, Any]


class InterruptRequest(BaseModel):
    game_id: str
    user_id: str
    transcript: str
