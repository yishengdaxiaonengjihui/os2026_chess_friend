"""REST 路由：新对局 / 落子全链路 / 语音打断 / 画像查询。

第二阶段：对局统计实时累加、对局终结(胜负/和棋)判定、长期记忆写入、
SQLite 画像 diff 更新。
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..core import (
    AvatarDispatcher,
    LLMClient,
    MemoryManager,
    PerformanceCommand,
    apply_move_to_fen,
    build_context,
    build_prompt,
    detect_move,
    make_default_fen,
    toggle_side,
)
from ..core.chess_engine import ai_move, legal_moves, position_status
from ..core.game_stats import (
    build_game_summary,
    finalize_game,
    fresh_stats,
    style_strength_diff,
    update_live_stats,
)
from ..db.database import append_move_record, finish_game_record, init_db, save_game_record
from ..models.schemas import (
    InterruptRequest,
    LLMOutput,
    MoveRequest,
    MoveResponse,
    NewGameRequest,
    NewGameResponse,
    ProfileResponse,
)

logger = logging.getLogger(__name__)

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
    memory = MemoryManager(user_id, game_id)
    # 跨对局累加的统计：从既有画像读取，无则新建
    profile = memory.profile_store.get(user_id)
    stats = profile.get("stats") or fresh_stats()
    sess = {
        "session_id": session_id,
        "game_id": game_id,
        "user_id": user_id,
        "personality": personality,
        "fen": fen,
        "prev_fen": fen,
        "move_index": 0,
        "game_over": False,
        "stats": stats,
        "capture_noted": False,  # 本局是否已为首次吃子写过长期记忆
        "memory": memory,
        "dispatcher": AvatarDispatcher(),
    }
    _sessions[game_id] = sess
    return sess


def _result_from_engine(user_fen: str, engine_res: dict) -> str | None:
    """对局结果：'win' | 'lose' | 'draw' | None(未结束)。

    engine_res 是 AI(黑) 视角；opponent = 用户。
    """
    if engine_res.get("opponent_checkmate"):
        return "lose"  # 用户被将死
    if engine_res.get("opponent_stalemate"):
        return "draw"  # 用户困毙
    if engine_res.get("from_sq") is None:
        # AI 无合法着法：需要判定是 AI 被将死(用户胜)还是困毙(和棋)
        status = position_status(user_fen, color="black")
        if status.get("checkmate"):
            return "win"
        if status.get("stalemate"):
            return "draw"
    return None


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
    logger.info("新对局创建 game_id=%s user=%s", sess["game_id"], req.user_id)
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
    if sess["game_over"]:
        raise HTTPException(status_code=400, detail="本局已结束，请新开对局")

    # 1) 合法性校验（用户执红）
    legal = legal_moves(sess["fen"], color="red")
    if (req.from_sq, req.to_sq) not in {(m["from"], m["to"]) for m in legal}:
        raise HTTPException(status_code=400, detail=f"非法着法 {req.from_sq}->{req.to_sq}")

    # 2) 用户落子 -> 新 FEN（轮到黑方）
    user_fen = toggle_side(apply_move_to_fen(sess["fen"], req.from_sq, req.to_sq))
    user_move = detect_move(sess["fen"], user_fen)
    sess["move_index"] += 1

    # 3) 引擎 AI 应手（AI 执黑）
    engine_res = ai_move(user_fen, color="black", move_number=sess["move_index"])
    ai_new_fen = toggle_side(engine_res["new_fen"])
    ai_move_obj = detect_move(user_fen, ai_new_fen) if engine_res["from_sq"] else None

    # 4) 棋局事件（吃子 / 将军 / 将死 / 困毙）
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
    elif engine_res.get("from_sq") is None:
        status = position_status(user_fen, color="black")
        if status.get("checkmate"):
            events.append("将死：AI 被将死，玩家获胜！")
        elif status.get("stalemate"):
            events.append("困毙：AI 无棋可走，和棋")

    # 5) 标准化博弈上下文（用户视角胜率）
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

    # 6) 统计实时累加（画像逐步生成）
    stats = update_live_stats(
        sess["stats"],
        user_move.to_dict(),
        ai_move_obj.to_dict() if ai_move_obj else None,
        user_win_prob,
    )

    # 7) 对局终结判定 -> 画像 + 长期记忆落盘
    result = _result_from_engine(user_fen, engine_res)
    if result is not None:
        sess["game_over"] = True
        finalize_game(stats, result)
        summary = build_game_summary(stats, result)
        sess["memory"].long_term.add(summary, metadata={"type": "game_summary", "game_id": sess["game_id"], "result": result})
        finish_game_record(sess["game_id"], result, ai_new_fen)
        logger.info("对局结束 game_id=%s result=%s", sess["game_id"], result)
    elif user_move.captured and not sess["capture_noted"]:
        # 本局首次吃子：写一条长期记忆，让「长期记忆」面板在对局中就开始填充
        sess["capture_noted"] = True
        sess["memory"].long_term.add(
            f"用户在第{sess['move_index']}手用{user_move.piece_name}吃掉对方{user_move.captured}，吃子主动、敢于交换。",
            metadata={"type": "capture", "game_id": sess["game_id"]},
        )

    # 8) 分层记忆召回
    sess["memory"].remember_turn("user", f"玩家走 {user_move.to_dict()}")
    recall = sess["memory"].recall(query=f"用户第{sess['move_index']}手棋 {user_move.piece}")

    # 9) 画像 diff 更新（棋风/棋力/开局 + 统计）
    diff = style_strength_diff(stats)
    diff["stats"] = stats
    profile = sess["memory"].profile_store.merge_diff(sess["user_id"], diff)

    # 10) 五层 Prompt -> LLM（强约束 JSON）
    messages = build_prompt(
        profile=profile,
        long_term_memories=recall["long_term"],
        board_context=ctx,
        short_term_history=recall["short_term"],
    )
    llm_out = _llm.chat(messages)
    sess["memory"].remember_turn("assistant", llm_out["speech_text"])

    # 11) 具身指令分发
    cmd = PerformanceCommand(
        speech_text=llm_out["speech_text"],
        emotion_tag=llm_out["emotion_tag"],
        action_tag=llm_out["action_tag"],
    )
    avatar_cmd = sess["dispatcher"].play_sync(cmd)

    # 12) 落盘棋谱
    append_move_record(sess["game_id"], sess["move_index"], user_move.to_dict(), engine_res, ai_new_fen, events)

    return MoveResponse(
        game_id=sess["game_id"],
        user_move=user_move.to_dict(),
        ai_move=engine_res,
        new_fen=ai_new_fen,
        events=events,
        llm_output=LLMOutput(**llm_out),
        avatar_command=avatar_cmd,
        long_term_memories=recall["long_term"],
        profile=profile,
    )


@router.get("/api/moves/legal")
def get_legal_moves(fen: str, color: str = "red") -> dict:
    """查询某方在当前局面的全部合法着法（供前端高亮与校验）。"""
    return {"moves": legal_moves(fen, color), "color": color, "fen": fen}


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
