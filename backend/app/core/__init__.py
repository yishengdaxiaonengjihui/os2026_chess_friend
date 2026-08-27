"""自研核心编排层（★ 本项目主要开源贡献）"""
from . import avatar_dispatcher, chess_context_parser, llm_client, memory_manager, prompt_builder
from .avatar_dispatcher import AvatarDispatcher, AvatarState, PerformanceCommand
from .chess_context_parser import build_context, detect_move, make_default_fen
from .llm_client import LLMClient
from .memory_manager import LongTermMemory, MemoryManager, ProfileStore, ShortTermMemory
from .prompt_builder import build_prompt

__all__ = [
    "AvatarDispatcher",
    "AvatarState",
    "PerformanceCommand",
    "build_context",
    "detect_move",
    "make_default_fen",
    "LLMClient",
    "LongTermMemory",
    "MemoryManager",
    "ProfileStore",
    "ShortTermMemory",
    "build_prompt",
]
