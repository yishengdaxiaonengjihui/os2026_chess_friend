"""自研核心编排层（★ 本项目主要开源贡献）"""
from . import (
    avatar_dispatcher,
    chess_context_parser,
    chess_engine,
    llm_client,
    memory_manager,
    prompt_builder,
)
from .avatar_dispatcher import AvatarDispatcher, AvatarState, PerformanceCommand
from .xmov_client import XmovAvatarClient
from .chess_context_parser import (
    apply_move_to_fen,
    build_context,
    detect_move,
    make_default_fen,
    toggle_side,
)
from .chess_engine import EngineError, ai_move, legal_moves, ping, position_status, score_to_win_prob
from .llm_client import LLMClient
from .memory_manager import LongTermMemory, MemoryManager, ProfileStore, ShortTermMemory
from .prompt_builder import build_prompt, system_role_for

__all__ = [
    "AvatarDispatcher",
    "AvatarState",
    "PerformanceCommand",
    "XmovAvatarClient",
    "EngineError",
    "ai_move",
    "legal_moves",
    "ping",
    "position_status",
    "score_to_win_prob",
    "apply_move_to_fen",
    "build_context",
    "detect_move",
    "make_default_fen",
    "toggle_side",
    "LLMClient",
    "LongTermMemory",
    "MemoryManager",
    "ProfileStore",
    "ShortTermMemory",
    "build_prompt",
    "system_role_for",
]
