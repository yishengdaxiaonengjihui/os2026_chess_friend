"""REST 路由：新对局 / 落子全链路 / 语音打断 / 画像查询。

第二阶段：对局统计实时累加、对局终结(胜负/和棋)判定、长期记忆写入、
SQLite 画像 diff 更新。
"""
from __future__ import annotations

import copy
import json
import logging
import time
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
from ..core.input_filter import InputFilter, is_noise
from ..core.narrative_driver import NARRATIVE_INTERVAL_MOVES, NarrativeContext, build_narrative, narrate
from ..core.memory_manager import detect_personal_info
from ..core.speech_trigger_decider import classify_strength, should_speak
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
    set_chat_pref as set_chat_pref_db,
    set_game_starred,
)
from ..models.schemas import (
    ChatRequest,
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
    ChatPrefRequest,
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

# 问题：结局必开口 —— LLM 输出为空/失败时的人格固定收尾台词（赢/输/和）
_ENDING_LINES = {
    "laozhang": {
        "win": "嘿，你赢了！这盘杀得真漂亮，我输得心服口服。",
        "lose": "这盘我赢了，承让承让。再来一盘，我可就认真了。",
        "draw": "困毙，和棋。谁也奈何不了谁，咱歇口气再开一盘。",
    },
    "xiaoya": {
        "win": "你赢了，下得真好！这盘我心服口服呢。",
        "lose": "这盘我赢了……承让啦，我们再来一盘吧。",
        "draw": "困毙了，和棋呢。咱们慢慢来，再下一盘吧。",
    },
}
_ENDING_EMOTION = {"win": "喜悦", "lose": "惋惜", "draw": "平静"}


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
    # 问题12：用户闲聊偏好（会话内快照，切后端设置下次开局生效）
    u = get_user(user_id)
    chat_pref = (u or {}).get("chat_pref") or "balanced"
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
        "chat_pref": chat_pref,
        # 问题1：言语触发决策状态（冷却 + 静默计数 + 上一步胜率）
        "last_speech_ts": None,
        "silent_streak": 0,
        "prev_win_prob": None,
        "memory": memory,
        "dispatcher": AvatarDispatcher(),
        "ai_opening": None,  # 执黑时 AI(红) 的首着
        "told_stories": set(),  # 主动叙事已讲过的片段（会话内去重）
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
        if status.get("is_checkmate"):
            return "win"
        if status.get("is_stalemate"):
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
        if status.get("is_checkmate"):
            events.append("将死：AI 被将死，玩家获胜！")
        elif status.get("is_stalemate"):
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
        ctx["game_result"] = result  # 结局指令注入 Prompt（结局必开口）
        sess["game_over"] = True
        finalize_game(stats, result)
        summary = build_game_summary(stats, result)
        sess["memory"].long_term.add(summary, metadata={"type": "game_summary", "game_id": sess["game_id"], "result": result})
        finish_game_record(sess["game_id"], result, ai_new_fen)
        logger.info("对局结束 game_id=%s result=%s", sess["game_id"], result)
    # 问题9：对局中的临时点评/吃子不写长期记忆，仅在整局结束生成摘要时写入（见上）。

    # 8) 分层记忆召回
    sess["memory"].remember_turn("user", f"玩家走 {user_move.to_dict()}")
    recall = sess["memory"].recall(query=f"第{sess['move_index']}手 用户 吃子 {user_move.piece_name}")

    # 9) 画像 diff 更新（棋风/棋力/开局 + 统计）
    diff = style_strength_diff(stats)
    diff["stats"] = stats
    profile = sess["memory"].profile_store.merge_diff(sess["user_id"], diff)

    # 10) 言语触发决策（问题1：取消“落子=必说话”）+ 五层 Prompt -> LLM（强约束 JSON）
    is_strong = classify_strength(
        events=events,
        user_move_captured=bool(user_move.captured),
        ai_move_captured=bool(ai_move_obj and ai_move_obj.captured),
        win_probability=user_win_prob,
        prev_win_probability=sess.get("prev_win_prob"),
    )
    sess["prev_win_prob"] = user_win_prob
    speak_now = True
    if _settings.speech_trigger_enabled:
        speak_now = should_speak(
            is_strong=is_strong,
            last_speech_ts=sess.get("last_speech_ts"),
            silent_streak=sess.get("silent_streak", 0),
        )
    if result is not None:
        speak_now = True  # 结局必开口：将死/困毙等终局绕过随机触发，必须说收尾
    if speak_now:
        messages = build_prompt(
            profile=profile,
            long_term_memories=recall["long_term"],
            board_context=ctx,
            short_term_history=recall["short_term"],
            system_role=system_role_for(sess["personality"]),
            chat_pref=sess.get("chat_pref"),
        )
        llm_out = _llm.chat(messages)
        # 问题5：第四层正则兜底，彻底清除坐标/记谱等机械话术
        llm_out["speech_text"] = sanitize_speech(llm_out["speech_text"])
        # 结局兜底：LLM 输出为空时用人格固定收尾台词（保证"你赢了"等必说）
        if result is not None and not (llm_out.get("speech_text") or "").strip():
            endings = _ENDING_LINES.get(sess["personality"], _ENDING_LINES["laozhang"])
            llm_out = {
                "speech_text": endings.get(result, endings["draw"]),
                "emotion_tag": _ENDING_EMOTION.get(result, "平静"),
                "action_tag": "idle",
            }
        sess["memory"].remember_turn("assistant", llm_out["speech_text"])
        sess["last_ai_speech"] = llm_out["speech_text"]  # 供 /api/chat 回声兜底
        # 11) 具身指令分发
        cmd = PerformanceCommand(
            speech_text=llm_out["speech_text"],
            emotion_tag=llm_out["emotion_tag"],
            action_tag=llm_out["action_tag"],
        )
        avatar_cmd = sess["dispatcher"].play_sync(cmd)
        sess["last_speech_ts"] = time.time()
        sess["silent_streak"] = 0
    else:
        # 静默思索：不调 LLM，只广播数字人思考动画
        llm_out = None
        avatar_cmd = sess["dispatcher"].think_only()
        sess["silent_streak"] = sess.get("silent_streak", 0) + 1

    # 问题4 + 问题13：主动叙事（参考 ProactiveAgent 节拍器）——
    # 大部分时间安静，只在「距上次主动叙事足够远」且「本步无强 LLM 点评」
    # 时才主动说一句简短家常话；按手数间隔限频，避免频繁开口。
    n_ctx = NarrativeContext(
        move_index=sess["move_index"],
        game_over=sess["game_over"],
        is_opening=sess["move_index"] <= 2,
        quiet_seconds=(time.time() - sess["last_speech_ts"]) if sess.get("last_speech_ts") else 999.0,
        has_event=bool(events),
        personality=sess["personality"],
        events=events,
        exclude=sess.get("told_stories", set()),
    )
    n_type = narrate(n_ctx)
    narrative_text = ""
    narr_emotion, narr_action = "平静", "idle"
    last_narr = sess.get("last_narrative_move", 0)
    # 限频：距上次主动叙事至少 NARRATIVE_INTERVAL_MOVES 手；本步 LLM 已说话则不叠
    if not speak_now and (sess["move_index"] - last_narr) >= NARRATIVE_INTERVAL_MOVES:
        narr = build_narrative(n_type, n_ctx)
        if narr and narr.get("text"):
            narrative_text = narr["text"]
            narr_emotion = narr.get("emotion_tag", "平静")
            narr_action = narr.get("action_tag", "idle")
    if narrative_text:
        sess["memory"].remember_turn("assistant", narrative_text)
        sess["last_narrative_move"] = sess["move_index"]
        sess["last_ai_speech"] = narrative_text  # 供 /api/chat 回声兜底
        sess.setdefault("told_stories", set()).add(narrative_text)  # 会话内去重
        # 主动叙事台词真正交给数字人播报（此前只入记忆、不开口）。
        # 与 LLM 点评走同一条具身指令链路：play_sync 入队 -> 前端 avatarAdapter.speak。
        avatar_cmd = sess["dispatcher"].play_sync(
            PerformanceCommand(speech_text=narrative_text, emotion_tag=narr_emotion, action_tag=narr_action)
        )
        # 叙事也算一次开口：更新发言时间戳、重置静默计数，避免与"连续静默保底"打架
        sess["last_speech_ts"] = time.time()
        sess["silent_streak"] = 0

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
        result=result,
        game_over=bool(sess["game_over"]),
        llm_output=LLMOutput(**llm_out) if llm_out else None,
        avatar_command=avatar_cmd,
        long_term_memories=recall["long_term"],
        profile=profile,
        narrative={"type": n_type.value, "text": narrative_text},
    )


@router.get("/api/moves/legal")
def get_legal_moves(fen: str, color: str = "red") -> dict:
    """查询某方在当前局面的全部合法着法（供前端高亮与校验）。"""
    return {"moves": legal_moves(fen, color), "color": color, "fen": fen}


@router.post("/api/games/{game_id}/personality")
def set_personality(game_id: str, req: PersonalityRequest) -> dict:
    """切换棋友人格（问题7：对局一旦开始全程锁定，仅开局前 new_game 时可选）。"""
    sess = _sessions.get(game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    if req.personality not in ("laozhang", "xiaoya"):
        raise HTTPException(status_code=400, detail="人格必须是 laozhang 或 xiaoya")
    if sess["move_index"] > 0 or sess["game_over"]:
        raise HTTPException(status_code=400, detail="对局已开始，棋友人格已锁定，请新开对局再选择棋友")
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
    """用户语音打断：终止数字人当前表演，清空队列。

    问题3：输入过滤 ——
    - 噪音判定：过短/纯标点/语气词输入直接忽略（不打断、不入记忆）。
    - 连续消息只响应最新：去抖窗口内连续输入仅保留最新一条（覆盖旧输入）。
    """
    sess = _sessions.get(req.game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    # 问题3：噪音判定
    if is_noise(req.transcript):
        return {"status": "noise_ignored", "reason": "noise", "queue_cleared": False}
    # 问题3：连续消息去抖（仅最新生效）
    gate = sess.setdefault("input_filter", InputFilter())
    verdict = gate.check(req.transcript)
    if verdict == "dedup":
        sess["memory"].short_term.replace_last_user(f"（用户打断）{req.transcript}")
        return {"status": "coalesced", "reason": "dedup", "queue_cleared": True}
    sess["dispatcher"].interrupt()
    sess["memory"].remember_turn("user", f"（用户打断）{req.transcript}")
    # 问题9：仅用户主动透露个人信息时写入长期记忆
    personal = detect_personal_info(req.transcript)
    if personal:
        sess["memory"].long_term.add(personal, metadata={"type": "personal", "game_id": sess["game_id"]})
    return {"status": "interrupted", "queue_cleared": True}


@router.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """语音/文字对话：用户说话 -> AI 用当前棋友人格回一句口语（步骤4）。

    复用问题3 输入过滤（噪音忽略 / 连续消息去抖）+ 分层记忆 + LLM：
    - 用户消息入短期记忆
    - 构建五层 Prompt（棋局上下文保持当前局面）生成一句回复
    - 返回 {speech_text, emotion_tag, action_tag, status}，前端 bargeIn 播报
    """
    sess = _sessions.get(req.game_id)
    if not sess:
        raise HTTPException(status_code=404, detail="game_id 不存在")
    # 回声兜底：数字人刚说完（3s 内），尾音被录进来——识别文本是最近一句
    # AI 台词的后缀/子串（>=3 字）即当作噪音丢弃，不进记忆不触发回复。
    ai_last = sess.get("last_ai_speech") or ""
    ts_last = sess.get("last_speech_ts") or 0
    t_text = (req.text or "").strip()
    if len(t_text) >= 3 and ai_last and (time.time() - ts_last) <= 3.0:
        if ai_last.endswith(t_text) or (len(t_text) >= 4 and t_text in ai_last):
            return {"status": "noise_ignored", "reason": "echo_tail", "reply": None}
    # 问题3：噪音判定
    if is_noise(req.text):
        return {"status": "noise_ignored", "reason": "noise", "reply": None}
    # 问题3：连续消息去抖（仅最新生效）
    gate = sess.setdefault("input_filter", InputFilter())
    verdict = gate.check(req.text)
    if verdict == "dedup":
        sess["memory"].short_term.replace_last_user(f"（用户说话）{req.text}")
    else:
        sess["memory"].remember_turn("user", f"（用户说话）{req.text}")
    # 问题9：主动透露个人信息时写入长期记忆
    personal = detect_personal_info(req.text)
    if personal:
        sess["memory"].long_term.add(personal, metadata={"type": "personal", "game_id": sess["game_id"]})

    # 分层记忆召回 + 画像
    recall = sess["memory"].recall(query=req.text)
    profile = sess["memory"].profile_store.get(sess["user_id"])
    # 对话上下文：保持当前棋局局面，让 AI 回复贴合"边下棋边聊"
    ctx = {
        "user_move": None,
        "ai_move": None,
        "material_text": "当前棋局进行中",
        "events": ["对方正在和你聊天"],
    }
    try:
        messages = build_prompt(
            profile=profile,
            long_term_memories=recall["long_term"],
            board_context=ctx,
            short_term_history=recall["short_term"],
            system_role=system_role_for(sess["personality"]),
            chat_pref=sess.get("chat_pref"),
        )
        llm_out = _llm.chat(messages)
        llm_out["speech_text"] = sanitize_speech(llm_out["speech_text"])
        sess["memory"].remember_turn("assistant", llm_out["speech_text"])
        sess["last_ai_speech"] = llm_out["speech_text"]  # 供回声兜底
        sess["last_speech_ts"] = time.time()
        sess["silent_streak"] = 0
        return {
            "status": "ok",
            "reply": {
                "speech_text": llm_out["speech_text"],
                "emotion_tag": llm_out["emotion_tag"],
                "action_tag": llm_out["action_tag"],
            },
        }
    except Exception as e:  # noqa: BLE001 LLM 失败时降级为口语库兜底
        logger.warning("chat LLM 失败，口语库兜底: %s", e)
        from ..core.prompt_builder import system_role_for as _sf  # noqa: F401 避免循环导入风险
        _ = _sf
        return {
            "status": "fallback",
            "reply": {"speech_text": "嗯，你说的我听着呢，咱先把这盘下好。", "emotion_tag": "平静", "action_tag": "nod"},
        }


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


@router.patch("/api/users/{user_id}/chat-pref")
def set_user_chat_pref(user_id: str, req: ChatPrefRequest) -> dict:
    """通用设置：闲聊三档偏好（quiet 安静 / balanced 普通 / chatty 爱聊天）。"""
    try:
        return set_chat_pref_db(user_id, req.chat_pref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
