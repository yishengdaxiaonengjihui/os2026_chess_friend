"""REST 路由：新对局 / 落子全链路 / 语音打断 / 画像查询。

第二阶段：对局统计实时累加、对局终结(胜负/和棋)判定、长期记忆写入、
SQLite 画像 diff 更新。
"""
from __future__ import annotations

import copy
import json
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
    system_role_for,
    toggle_side,
    ws_hub,
)
from ..core.chess_engine import ai_move, legal_moves, position_status, score_to_win_prob
from ..core.term_filter import sanitize_speech
from ..core.model_registry import get_runtime_model, list_models, set_runtime_model
from ..core.game_stats import (
    build_game_summary,
    finalize_game,
    fresh_stats,
    style_strength_diff,
    update_live_stats,
)
from ..db.database import (
    append_move_record,
    clear_game_result,
    create_user as create_user_db,
    decrement_move_count,
    delete_game_record,
    delete_user as delete_user_db,
    finish_game_record,
    get_game_moves,
    get_game_start_fen,
    get_user,
    init_db,
    list_games,
    list_users,
    remove_last_move_record,
    rename_user as rename_user_db,
    save_game_record,
    set_game_starred,
)
from ..models.schemas import (
    GamesListResponse,
    InterruptRequest,
    LLMOutput,
    ModelSwitchRequest,
    MoveRequest,
    MoveResponse,
    NewGameRequest,
    NewGameResponse,
    PersonalityRequest,
    ProfileResponse,
    StarRequest,
    UndoResponse,
    UserCreateRequest,
    UserLoginRequest,
    UserRenameRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 会话运行时状态（内存）：game_id -> GameSession
_sessions: dict[str, dict] = {}
_llm = LLMClient()
_settings = get_settings()


def _new_session(
    user_id: str,
    personality: str,
    side: str = "red",
    strength: str = "auto",
) -> dict:
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
        "user_color": side if side in ("red", "black") else "red",
        "strength": strength if strength in ("low", "medium", "high", "auto") else "auto",
        "fen": fen,
        "prev_fen": fen,
        "move_index": 0,
        "game_over": False,
        "stats": stats,
        "capture_noted": False,  # 本局是否已为首次吃子写过长期记忆
        "memory": memory,
        "dispatcher": AvatarDispatcher(),
        "ai_opening": None,  # 执黑时 AI(红) 的首着
    }
    # 数字人状态广播 -> 对局 WS 连接
    sess["dispatcher"].set_broadcaster(
        lambda state, cmd: ws_hub.broadcast_avatar_state(sess["game_id"], state, cmd)
    )
    # 执黑：AI(红) 先走第一手（开局库着法）
    if sess["user_color"] == "black":
        try:
            er = ai_move(
                fen,
                color="red",
                difficulty=_strength_to_difficulty(sess),
                move_number=1,
            )
            if er["from_sq"]:
                sess["fen"] = toggle_side(er["new_fen"])  # 轮到黑方(玩家)
                sess["prev_fen"] = fen
                sess["ai_opening"] = {
                    "from_sq": er["from_sq"],
                    "to_sq": er["to_sq"],
                    "piece": er["piece"],
                    "new_fen": sess["fen"],
                }
        except Exception:  # noqa: BLE001 引擎异常时退化为正常开局
            sess["user_color"] = "red"
            sess["ai_opening"] = None
            sess["fen"] = fen
            sess["prev_fen"] = fen
    _sessions[game_id] = sess
    return sess


def _strength_to_difficulty(sess: dict) -> int | None:
    """棋力选择 -> 引擎搜索深度：低1 / 中2 / 高5 / 自动按玩家平均胜率自适应。"""
    st = sess.get("strength", "auto")
    if st == "low":
        return 1
    if st == "medium":
        return 2
    if st == "high":
        return 5
    p = (sess.get("stats") or {}).get("avg_user_win_prob")
    if p is None:
        return None  # 用配置默认
    if p < 0.4:
        return 2
    if p > 0.6:
        return 5
    return 3


def _result_from_engine(
    user_fen: str,
    ai_new_fen: str,
    engine_res: dict,
    user_color: str = "red",
) -> str | None:
    """对局结果：'win' | 'lose' | 'draw' | None(未结束)。

    engine_res 是 AI 视角；opponent = 用户。
    结局只允许三种：用户被将死(lose)、用户将死 AI(win)、和棋(draw)。
    """
    ai_color = "black" if user_color == "red" else "red"
    user_king = "K" if user_color == "red" else "k"   # 玩家主将
    ai_king = "k" if user_color == "red" else "K"     # AI 主将
    # 兜底：将帅被吃/消失即判胜负（送吃等边界情形）
    if user_king not in ai_new_fen:
        return "lose"   # 玩家主将不在 -> 用户被将死
    if ai_king not in ai_new_fen:
        return "win"    # AI 主将不在 -> 用户将死 AI
    if engine_res.get("opponent_checkmate"):
        return "lose"  # 用户被将死
    if engine_res.get("opponent_stalemate"):
        return "draw"  # 用户困毙
    if engine_res.get("from_sq") is None:
        # AI 无合法着法：需要判定是 AI 被将死(用户胜)还是困毙(和棋)
        status = position_status(user_fen, color=ai_color)
        if status.get("checkmate"):
            return "win"
        if status.get("stalemate"):
            return "draw"
    return None


def _persona_comment(sess: dict, topic: str, extra: str = "") -> dict:
    """按当前人格生成一句简短回应（LLM 失败自动回退固定台词）。"""
    system = system_role_for(sess["personality"])
    prompt = (
        "你正在陪独居老人李大爷下中国象棋。"
        f"棋友刚刚{topic}。{extra}"
        "请用你的口吻简短回应一句（不超过25字），口语化、符合你的性格。"
        '输出严格为 JSON 对象：{"speech_text":"...","emotion_tag":"...","action_tag":"..."}。'
    )
    try:
        out = _llm.chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        if out and out.get("speech_text"):
            out["speech_text"] = sanitize_speech(out["speech_text"])  # 问题5 第四层净化
            return out
    except Exception:  # noqa: BLE001
        pass
    fallback = {
        "draw_accepted": {"speech_text": "行，这局面僵住了，咱就和了吧，下得不错！", "emotion_tag": "平静", "action_tag": "nod"},
        "draw_declined": {"speech_text": "哈哈不急，我这还占着上风呢，再战几个回合！", "emotion_tag": "得意", "action_tag": "wave"},
        "resign": {"speech_text": "没事老哥，胜负常有，咱再开一局！", "emotion_tag": "鼓励", "action_tag": "nod"},
    }
    return fallback.get(topic, fallback["resign"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_mode": "mock" if _llm.mock_mode else "real",
        "digital_human_enabled": _settings.enable_digital_human,
    }


@router.post("/api/games", response_model=NewGameResponse)
def new_game(req: NewGameRequest) -> NewGameResponse:
    sess = _new_session(req.user_id, req.personality, req.side, req.strength)
    logger.info(
        "新对局创建 game_id=%s user=%s side=%s strength=%s",
        sess["game_id"], req.user_id, sess["user_color"], sess["strength"],
    )
    return NewGameResponse(
        game_id=sess["game_id"],
        user_id=req.user_id,
        fen=sess["fen"],
        side=sess["user_color"],
        strength=sess["strength"],
        digital_human_enabled=_settings.enable_digital_human,
        ai_opening=sess.get("ai_opening"),
    )


@router.post("/api/moves", response_model=MoveResponse)
def make_move(req: MoveRequest) -> MoveResponse:
    sess = _sessions.get(req.game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在，请先创建对局")
    if sess["game_over"]:
        raise HTTPException(status_code=400, detail="本局已结束，请新开对局")

    user_color = sess.get("user_color", "red")
    ai_color = "black" if user_color == "red" else "red"
    user_king = "K" if user_color == "red" else "k"   # 玩家主将
    ai_king = "k" if user_color == "red" else "K"     # AI 主将

    # 1) 合法性校验（engine 已过滤“送吃”——走完己方老帅受攻的着法）
    legal = legal_moves(sess["fen"], color=user_color)
    if (req.from_sq, req.to_sq) not in {(m["from"], m["to"]) for m in legal}:
        raise HTTPException(
            status_code=400,
            detail=f"这一步走不得：会把老帅送上门或违反规则（{req.from_sq}→{req.to_sq}），请重新选择",
        )

    # 2) 用户落子 -> 轮到 AI 的新 FEN
    user_fen = toggle_side(apply_move_to_fen(sess["fen"], req.from_sq, req.to_sq))
    user_move = detect_move(sess["fen"], user_fen)
    sess["move_index"] += 1

    # 兜底：用户落子后己方主将必须健在（引擎已滤送吃，此处防御）
    if user_king not in user_fen:
        raise HTTPException(status_code=400, detail="这一步走不得：老帅出险（送吃）")

    # 悔棋支持：快照本轮开始前的统计（undo 时回滚）
    sess["stats_snapshot"] = copy.deepcopy(sess["stats"])

    # 3) 引擎 AI 应手；用户直接吃掉 AI 主将则立即判胜，不再让引擎走
    if ai_king not in user_fen:
        engine_res = {
            "from_sq": None, "to_sq": None, "piece": None,
            "new_fen": user_fen, "score": 10000, "win_probability": 1.0,
            "opponent_in_check": False, "opponent_checkmate": False, "opponent_stalemate": False,
        }
        ai_new_fen = user_fen
        ai_move_obj = None
    else:
        engine_res = ai_move(
            user_fen,
            color=ai_color,
            difficulty=_strength_to_difficulty(sess),
            move_number=sess["move_index"],
        )
        ai_new_fen = toggle_side(engine_res["new_fen"])
        ai_move_obj = detect_move(user_fen, ai_new_fen) if engine_res["from_sq"] else None

    # 4) 棋局事件（吃子 / 将军 / 将死 / 困毙）
    events: list[str] = []
    ai_king_lost = ai_king not in ai_new_fen
    user_king_lost = user_king not in ai_new_fen
    if user_move.captured:
        events.append(f"玩家吃子：吃掉对方{user_move.captured_name}")
    if ai_move_obj and ai_move_obj.captured:
        events.append(f"AI 吃子：吃掉玩家{ai_move_obj.captured_name}")
    if ai_king_lost:
        events.append("将死：对方主将被吃，玩家获胜！")
    elif user_king_lost:
        events.append("将死：我方主将被吃，AI 获胜")
    elif engine_res.get("opponent_in_check"):
        events.append("将军：玩家被将军！")
    if engine_res.get("opponent_checkmate") and not ai_king_lost and not user_king_lost:
        events.append("将死：玩家被将死，AI 获胜")
    elif engine_res.get("opponent_stalemate"):
        events.append("困毙：玩家无棋可走")
    elif engine_res.get("from_sq") is None and not ai_king_lost and not user_king_lost:
        status = position_status(user_fen, color=ai_color)
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
    result = _result_from_engine(user_fen, ai_new_fen, engine_res, user_color)
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
            f"用户在第{sess['move_index']}手用{user_move.piece_name}吃掉对方{user_move.captured_name}，吃子主动、敢于交换。",
            metadata={"type": "capture", "game_id": sess["game_id"]},
        )

    # 8) 分层记忆召回
    sess["memory"].remember_turn("user", f"玩家走 {user_move.to_dict()}")
    recall = sess["memory"].recall(query=f"第{sess['move_index']}手 用户 吃子 {user_move.piece_name}")

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
        system_role=system_role_for(sess["personality"]),
    )
    llm_out = _llm.chat(messages)
    # 问题5：第四层正则兜底，彻底清除坐标/记谱等机械话术
    llm_out["speech_text"] = sanitize_speech(llm_out["speech_text"])
    sess["memory"].remember_turn("assistant", llm_out["speech_text"])

    # 11) 具身指令分发
    cmd = PerformanceCommand(
        speech_text=llm_out["speech_text"],
        emotion_tag=llm_out["emotion_tag"],
        action_tag=llm_out["action_tag"],
    )
    avatar_cmd = sess["dispatcher"].play_sync(cmd)

    # 12) 落盘棋谱 + 对局事件广播（供前端实时感知）
    append_move_record(sess["game_id"], sess["move_index"], user_move.to_dict(), engine_res, ai_new_fen, events)
    ws_hub.broadcast_game_event(sess["game_id"], "move")
    if sess["game_over"]:
        ws_hub.broadcast_game_event(sess["game_id"], f"result:{sess['stats'].get('last_result')}")

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


@router.post("/api/games/{game_id}/personality")
def set_personality(game_id: str, req: PersonalityRequest) -> dict:
    """切换棋友人格：更新 LLM 人设，并清空本局聊天记忆让新人格重新开始。"""
    sess = _sessions.get(game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    if req.personality not in ("laozhang", "xiaoya"):
        raise HTTPException(status_code=400, detail="人格必须是 laozhang 或 xiaoya")
    sess["personality"] = req.personality
    sess["memory"].short_term.clear()
    return {"status": "ok", "personality": req.personality, "game_id": game_id}


@router.post("/api/games/{game_id}/undo", response_model=UndoResponse)
def undo_move(game_id: str) -> UndoResponse:
    """悔棋一步：回退用户与 AI 的上一轮（棋盘、统计、棋谱、对局状态）。"""
    sess = _sessions.get(game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    if sess["move_index"] <= 0:
        raise HTTPException(status_code=400, detail="开局第一手，没有可悔的棋")
    # 棋盘与手数回退
    sess["fen"] = sess["prev_fen"]
    sess["move_index"] -= 1
    sess["game_over"] = False
    # 统计回滚到本轮开始前
    if "stats_snapshot" in sess:
        sess["stats"] = sess["stats_snapshot"]
    # 棋谱：删最后一轮记录、回退手数、清终局结果
    remove_last_move_record(game_id)
    decrement_move_count(game_id)
    clear_game_result(game_id)
    # 短期聊天记忆：弹掉末尾 user+assistant 两轮
    turns = sess["memory"].short_term.turns
    for _ in range(2):
        if turns:
            turns.pop()
    ws_hub.broadcast_game_event(game_id, "undo")
    return UndoResponse(status="ok", fen=sess["fen"], move_index=sess["move_index"], game_over=False)


@router.post("/api/games/{game_id}/draw")
def draw_offer(game_id: str) -> dict:
    """和棋：AI 按当前局面自动判断是否同意。同意则终局为和棋。"""
    sess = _sessions.get(game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    if sess["game_over"]:
        raise HTTPException(status_code=400, detail="本局已结束")

    # AI 判断：按当前局面用户胜率决定是否同意和棋（按执子方评估）
    user_color = sess.get("user_color", "red")
    status = position_status(sess["fen"], color=user_color)
    ev = status.get("evaluate")
    user_win_prob = round(score_to_win_prob(ev), 4) if ev is not None else 0.5
    accepted = user_win_prob >= 0.4  # AI 无明显优势即同意
    topic = "draw_accepted" if accepted else "draw_declined"
    llm_out = _persona_comment(sess, topic)

    sess["memory"].remember_turn("user", "（棋友提出和棋，AI " + ("同意" if accepted else "暂不同意") + "）")
    sess["memory"].remember_turn("assistant", llm_out["speech_text"])
    cmd = PerformanceCommand(
        speech_text=llm_out["speech_text"],
        emotion_tag=llm_out["emotion_tag"],
        action_tag=llm_out["action_tag"],
    )
    sess["dispatcher"].play_sync(cmd)

    resp: dict = {
        "accepted": accepted,
        "user_win_prob": user_win_prob,
        "llm_output": llm_out,
        "game_over": False,
    }
    if accepted:
        sess["game_over"] = True
        finalize_game(sess["stats"], "draw")
        summary = build_game_summary(sess["stats"], "draw")
        sess["memory"].long_term.add(
            summary, metadata={"type": "game_summary", "game_id": game_id, "result": "draw"}
        )
        finish_game_record(game_id, "draw", sess["fen"])
        resp["game_over"] = True
        ws_hub.broadcast_game_event(game_id, "result:draw")
    return resp


@router.post("/api/games/{game_id}/resign")
def resign(game_id: str) -> dict:
    """认输：本局判负（用户视角 lose），终局。"""
    sess = _sessions.get(game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    if sess["game_over"]:
        raise HTTPException(status_code=400, detail="本局已结束")

    sess["game_over"] = True
    finalize_game(sess["stats"], "lose")
    summary = build_game_summary(sess["stats"], "lose")
    sess["memory"].long_term.add(
        summary, metadata={"type": "game_summary", "game_id": game_id, "result": "lose"}
    )
    finish_game_record(game_id, "lose", sess["fen"])

    llm_out = _persona_comment(sess, "resign")
    sess["memory"].remember_turn("user", "（棋友认输）")
    sess["memory"].remember_turn("assistant", llm_out["speech_text"])
    cmd = PerformanceCommand(
        speech_text=llm_out["speech_text"],
        emotion_tag=llm_out["emotion_tag"],
        action_tag=llm_out["action_tag"],
    )
    sess["dispatcher"].play_sync(cmd)
    ws_hub.broadcast_game_event(game_id, "result:lose")
    return {"status": "ok", "game_over": True, "result": "lose", "llm_output": llm_out}


@router.get("/api/games", response_model=GamesListResponse)
def list_user_games(user_id: str) -> GamesListResponse:
    """棋谱库：列出该用户的历史对局（新的在前）。"""
    return GamesListResponse(games=list_games(user_id))


@router.get("/api/games/{game_id}/moves")
def user_game_moves(game_id: str) -> dict:
    """棋谱库：返回某对局的逐手记录（含开局 FEN，供前端回放）。"""
    return {
        "game_id": game_id,
        "start_fen": get_game_start_fen(game_id),
        "moves": get_game_moves(game_id),
    }


@router.post("/api/interrupt")
def interrupt(req: InterruptRequest) -> dict:
    """用户语音打断：终止数字人当前表演，清空队列。"""
    sess = _sessions.get(req.game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    sess["dispatcher"].interrupt()
    sess["memory"].remember_turn("user", f"（用户打断）{req.transcript}")
    return {"status": "interrupted", "queue_cleared": True}


# ---------------- 多用户：账号 ----------------
@router.post("/api/users")
def create_account(req: UserCreateRequest) -> dict:
    """创建账号（昵称去重，已存在则复用）。"""
    return create_user_db(req.nickname)


@router.get("/api/users")
def all_users() -> dict:
    """全部账号（登录页选择用）。"""
    return {"users": list_users()}


@router.post("/api/users/login")
def login(req: UserLoginRequest) -> dict:
    """选择账号登录（本地演示：仅校验存在性）。"""
    u = get_user(req.user_id)
    if not u:
        raise HTTPException(status_code=404, detail="账号不存在，请先创建")
    return {"ok": True, "user": u}


@router.patch("/api/users/{user_id}")
def rename_account(user_id: str, req: UserRenameRequest) -> dict:
    """账号管理：修改昵称。"""
    try:
        return rename_user_db(user_id, req.nickname)
    except ValueError:
        raise HTTPException(status_code=404, detail="账号不存在")


@router.delete("/api/users/{user_id}")
def remove_account(user_id: str) -> dict:
    """账号管理：删除账号及其全部数据（画像/记忆/棋谱）。"""
    delete_user_db(user_id)
    return {"status": "ok", "user_id": user_id}


# ---------------- 棋谱管理：加精 / 删除 ----------------
@router.post("/api/games/{game_id}/star")
def star_game(game_id: str, req: StarRequest) -> dict:
    set_game_starred(game_id, req.starred)
    return {"status": "ok", "game_id": game_id, "starred": req.starred}


@router.delete("/api/games/{game_id}")
def delete_game(game_id: str) -> dict:
    """删除整局棋谱（含着法记录）。"""
    delete_game_record(game_id)
    _sessions.pop(game_id, None)
    return {"status": "ok", "game_id": game_id}


# ---------------- 通用设置：模型管理 ----------------
@router.get("/api/models")
def models_list() -> dict:
    """可用模型清单 + 当前生效模型。"""
    return {
        "models": list_models(_settings.llm_model),
        "current": get_runtime_model() or _settings.llm_model,
    }


@router.post("/api/models")
def switch_model(req: ModelSwitchRequest) -> dict:
    """切换运行时模型（失败自动回退配置默认模型）。"""
    try:
        set_runtime_model(req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "model": req.model}


@router.get("/api/profiles/{user_id}", response_model=ProfileResponse)
def get_profile(user_id: str) -> ProfileResponse:
    from ..db.profile_repo import get_profile as load_profile

    return ProfileResponse(user_id=user_id, profile=load_profile(user_id))
