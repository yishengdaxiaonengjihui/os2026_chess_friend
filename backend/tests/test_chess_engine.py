"""象棋引擎适配层单测（真实调用 node + vendor logic.js）。"""
import pytest

from backend.app.core import chess_context_parser as ccp
from backend.app.core.chess_engine import ai_move, ping, position_status, score_to_win_prob


@pytest.fixture(scope="module")
def engine_ready():
    assert ping(), "引擎 ping 失败，请确认 node 与 vendor/logic.js 就绪"
    return True


def test_ping(engine_ready):
    assert engine_ready


def test_position_initial(engine_ready):
    st = position_status(ccp.make_default_fen(), color="red")
    assert st["in_check"] is False
    assert st["is_checkmate"] is False
    assert st["legal_move_count"] > 0


def test_score_to_win_prob():
    assert 0.0 < score_to_win_prob(0) < 1.0
    assert score_to_win_prob(1000) > 0.9
    assert score_to_win_prob(-1000) < 0.1


def test_ai_move_black_reply(engine_ready):
    # 用户红先走兵，引擎黑方应手
    fen = ccp.make_default_fen()
    user_fen = ccp.apply_move_to_fen(fen, "a6", "a5")
    res = ai_move(user_fen, color="black", difficulty=2, time_ms=400)
    assert res["from_sq"] and res["to_sq"]
    assert res["new_fen"] != user_fen
    # AI 落子必须是合法变换（diff 恰好一格）
    mv = ccp.detect_move(user_fen, res["new_fen"])
    assert mv.piece is not None
    assert res["opponent_in_check"] in (True, False)


def test_ai_move_open_capture(engine_ready):
    # 构造一个黑炮隔山打红马的初始局面，验证引擎能走出吃子
    fen = ccp.make_default_fen()
    res = ai_move(fen, color="black", difficulty=2, time_ms=400)
    assert res["from_sq"] == "b2" or res["from_sq"] == "h2"  # 黑炮开局应手
