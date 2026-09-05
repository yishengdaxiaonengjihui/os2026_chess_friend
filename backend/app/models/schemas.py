"""Pydantic 数据模型（API 层请求/响应契约）。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class NewGameRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    personality: str = Field("laozhang", description="人格：laozhang / xiaoya")
    side: str = Field("red", description="玩家执子：red 先 / black 后")
    strength: str = Field("auto", description="AI 棋力：low / medium / high / auto")


class NewGameResponse(BaseModel):
    game_id: str
    user_id: str
    fen: str
    side: str
    strength: str
    digital_human_enabled: bool
    ai_opening: Optional[dict[str, Any]] = None


class UserCreateRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=32)


class UserRenameRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=32)


class UserLoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)


class StarRequest(BaseModel):
    starred: bool


class ModelSwitchRequest(BaseModel):
    model: str = Field(..., min_length=1)


class MoveRequest(BaseModel):
    game_id: str
    user_id: str
    from_sq: str
    to_sq: str
    thinking_text: Optional[str] = None


class LegalMovesResponse(BaseModel):
    moves: list[dict[str, str]]
    color: str
    fen: str


class LLMOutput(BaseModel):
    speech_text: str
    emotion_tag: str
    action_tag: str


class MoveResponse(BaseModel):
    game_id: str
    user_move: dict[str, Any]
    ai_move: dict[str, Any]
    new_fen: str
    events: list[str]
    llm_output: Optional[LLMOutput] = None  # 问题1：言语触发决策后可能静默（不发言）
    avatar_command: Optional[dict[str, Any]] = None
    long_term_memories: list[str]
    profile: dict[str, Any]
    # 问题4：主动叙事框架（占位）—— 透出叙事决策结果，内容当前为空
    narrative: Optional[dict[str, Any]] = None


class ProfileResponse(BaseModel):
    user_id: str
    profile: dict[str, Any]


class InterruptRequest(BaseModel):
    game_id: str
    user_id: str
    transcript: str


class ChatRequest(BaseModel):
    game_id: str
    user_id: str
    text: str  # 用户说话转写的文字


class PersonalityRequest(BaseModel):
    personality: str = Field(..., description="人格：laozhang / xiaoya")


class ChatPrefRequest(BaseModel):
    chat_pref: str = Field(..., description="闲聊偏好：quiet / balanced / chatty")


class UndoResponse(BaseModel):
    status: str
    fen: str
    move_index: int
    game_over: bool


class GamesListResponse(BaseModel):
    games: list[dict[str, Any]]
