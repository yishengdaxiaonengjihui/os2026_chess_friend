"""REST 路由：新对局 / 落子全链路 / 语音打断 / 画像查询。"""
from __future__ import annotations

import uuid

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

from ..config import get_settings
from ..core import (
    AvatarDispatcher,
    LLMClient,
    MemoryManager,
    PerformanceCommand,
    build_context,
    build_prompt,
    detect_move,
    make_default_fen,
)
from ..core.chess_engine import ai_move
from ..db.database import append_move_record, init_db, save_game_record
from ..models.schemas import (
    InterruptRequest,
    MoveRequest,
    MoveResponse,
    NewGameRequest,
    NewGameResponse,
    ProfileResponse,
    LLMOutput,
)

router = APIRouter()

# 会话运行时状态（内存）：game_id -> GameSession
_sessions: dict[str, dict] = {}
_llm = LLMClient()
_settings = get_settings()


def _new_session(user_id: str, personality: str) -> dict:
    game_id = uuid.uuid4().hex[:12]
    session_id = uuid.uuid4().hex[:12]
    fen = make_default_fen()
    init_db()
    save_game_record(game_id, session_id, user_id, fen)
    sess = {
        "session_id": session_id,
        "game_id": game_id,
        "user_id": user_id,
        "personality": personality,
        "fen": fen,
        "prev_fen": fen,
        "move_index": 0,
        "memory": MemoryManager(user_id, game_id),
        "dispatcher": AvatarDispatcher(),
    }
    _sessions[game_id] = sess
    return sess


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_mode": "mock" if _llm.mock_mode else "real",
        "digital_human_enabled": _settings.enable_digital_human,
    }


@router.post("/api/games", response_model=NewGameResponse)
def new_game(req: NewGameRequest) -> NewGameResponse:
    sess = _new_session(req.user_id, req.personality)
    logger.info("新对局创建 game_id={} user={}", sess["game_id"], req.user_id)
    return NewGameResponse(
        game_id=sess["game_id"],
        user_id=req.user_id,
        fen=sess["fen"],
        side="w",
        digital_human_enabled=_settings.enable_digital_human,
    )


@router.post("/api/moves", response_model=MoveResponse)
def make_move(req: MoveRequest) -> MoveResponse:
    sess = _sessions.get(req.game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在，请先创建对局")

    # 1) 棋局状态解析：还原用户这手棋（结构化）
    user_move = detect_move(sess["fen"], req.fen)
    sess["move_index"] += 1

    # 2) 引擎 AI 应手（用户执红 -> AI 执黑）
    engine_res = ai_move(req.fen, color="black", move_number=sess["move_index"])
    ai_new_fen = engine_res["new_fen"]
    ai_move_obj = detect_move(req.fen, ai_new_fen) if engine_res["from_sq"] else None

    # 3) 棋局事件（吃子 / 将军 / 将死 / 困毙）
    events: list[str] = []
    if user_move.captured:
        events.append(f"玩家吃子：吃掉对方{user_move.captured}")
    if ai_move_obj and ai_move_obj.captured:
        events.append(f"AI 吃子：吃掉玩家{ai_move_obj.captured}")
    if engine_res.get("opponent_in_check"):
        events.append("将军：玩家被将军！")
    if engine_res.get("opponent_checkmate"):
        events.append("将死：玩家被将死，AI 获胜")
    elif engine_res.get("opponent_stalemate"):
        events.append("困毙：玩家无棋可走")

    # 4) 标准化博弈上下文（用户视角胜率）
    user_win_prob = round(1 - engine_res["win_probability"], 4) if engine_res["win_probability"] is not None else None
    ctx = build_context(
        user_move=user_move,
        ai_move=ai_move_obj,
        fen=ai_new_fen,
        win_probability=user_win_prob,
        events=events,
    )
    sess["prev_fen"] = sess["fen"]
    sess["fen"] = ai_new_fen

    # 5) 分层记忆召回
    sess["memory"].remember_turn("user", f"玩家走 {user_move.to_dict()}")
    recall = sess["memory"].recall(query=f"用户第{sess['move_index']}手棋 {user_move.piece}")

    # 6) 五层 Prompt -> LLM（强约束 JSON）
    messages = build_prompt(
        profile=recall["profile"],
        long_term_memories=recall["long_term"],
        board_context=ctx,
        short_term_history=recall["short_term"],
    )
    llm_out = _llm.chat(messages)
    sess["memory"].remember_turn("assistant", llm_out["speech_text"])

    # 7) 具身指令分发
    cmd = PerformanceCommand(
        speech_text=llm_out["speech_text"],
        emotion_tag=llm_out["emotion_tag"],
        action_tag=llm_out["action_tag"],
    )
    avatar_cmd = sess["dispatcher"].play_sync(cmd)

    # 8) 落盘棋谱
    append_move_record(sess["game_id"], sess["move_index"], user_move.to_dict(), engine_res, ai_new_fen, events)

    return MoveResponse(
        game_id=sess["game_id"],
        ai_move=engine_res,
        new_fen=ai_new_fen,
        events=events,
        llm_output=LLMOutput(**llm_out),
        avatar_command=avatar_cmd,
        long_term_memories=recall["long_term"],
        profile=recall["profile"],
    )


@router.post("/api/interrupt")
def interrupt(req: InterruptRequest) -> dict:
    """用户语音打断：终止数字人当前表演，清空队列。"""
    sess = _sessions.get(req.game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    sess["dispatcher"].interrupt()
    sess["memory"].remember_turn("user", f"（用户打断）{req.transcript}")
    return {"status": "interrupted", "queue_cleared": True}


@router.get("/api/profiles/{user_id}", response_model=ProfileResponse)
def get_profile(user_id: str) -> ProfileResponse:
    from ..db.profile_repo import get_profile as load_profile

    return ProfileResponse(user_id=user_id, profile=load_profile(user_id))
