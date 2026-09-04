"""问题8：引擎走法多样性 —— 开局库加权随机 + 中局候选加权随机。

conftest 默认关闭多样性（ENGINE_DIVERSITY=0）保证链路测试确定性；
本文件显式开启 diversity 验证多样性行为。
"""
import pytest

from backend.app.core import chess_context_parser as ccp
from backend.app.core.chess_engine import ai_move, legal_moves, ping

DEFAULT_FEN = ccp.make_default_fen()


@pytest.fixture(scope="module")
def engine_ready():
    assert ping(), "引擎 ping 失败"
    return True


def _legal_from_to(fen, color):
    return {m["from"] + m["to"] for m in legal_moves(fen, color)}


def test_diversity_disabled_deterministic_opening(engine_ready):
    """关闭多样性时：开局固定走中炮（原开局库行为），多跑一致。"""
    moves = {
        ai_move(DEFAULT_FEN, color="red", difficulty=2, move_number=1, diversity=False)["from_sq"]
        for _ in range(5)
    }
    assert moves == {"b7"}  # 中炮（红炮 b7 平中）


def test_diversity_opening_produces_multiple_lines(engine_ready):
    """开启多样性：开局阶段应出现多种不同开局着法（加权随机开局库）。"""
    froms = []
    for _ in range(24):
        res = ai_move(DEFAULT_FEN, color="red", difficulty=5, move_number=1, diversity=True)
        assert res["from_sq"] and res["to_sq"]
        froms.append(res["from_sq"] + res["to_sq"])
    distinct = set(froms)
    # 候选开局库含 中炮/仙人指路/飞相/跳马/上士/边兵 多路着法
    assert len(distinct) >= 2, f"开局应有多样性，实际只有 {distinct}"


def test_diversity_moves_are_legal(engine_ready):
    """开启多样性：开局与中局选出的着法都必须是合法着法。"""
    legal = _legal_from_to(DEFAULT_FEN, "red")
    for _ in range(12):
        res = ai_move(DEFAULT_FEN, color="red", difficulty=5, move_number=1, diversity=True)
        assert res["from_sq"] + res["to_sq"] in legal
    # 中局局面（黑炮中宫，红士角炮开局后）
    mid_fen = "r1bakabnr/9/1cn3c1C/p1p1p1p1p/9/9/P1P1P1P1P/1C1C5/9/RNBAKABNR w - - 0 1"
    legal_mid = _legal_from_to(mid_fen, "red")
    for _ in range(12):
        res = ai_move(mid_fen, color="red", difficulty=5, move_number=8, diversity=True)
        assert res["from_sq"] + res["to_sq"] in legal_mid


def test_diversity_midgame_produces_multiple_moves(engine_ready):
    """开启多样性：中局同一局面应出现多种候选着法（加权随机）。"""
    mid_fen = "r1bakabnr/9/1cn3c1C/p1p1p1p1p/9/9/P1P1P1P1P/1C1C5/9/RNBAKABNR w - - 0 1"
    moves = []
    for _ in range(24):
        res = ai_move(mid_fen, color="red", difficulty=5, move_number=8, diversity=True)
        assert res["from_sq"] and res["to_sq"]
        moves.append(res["from_sq"] + res["to_sq"])
    distinct = set(moves)
    assert len(distinct) >= 2, f"中局应有多样性，实际只有 {distinct}"


def test_diversity_black_reply_still_legal(engine_ready):
    """黑方开局应手开启多样性后仍为合法着法（且可用）。"""
    fen = ccp.apply_move_to_fen(DEFAULT_FEN, "a6", "a5")
    legal = _legal_from_to(fen, "black")
    seen = set()
    for _ in range(12):
        res = ai_move(fen, color="black", difficulty=5, move_number=2, diversity=True)
        assert res["from_sq"] + res["to_sq"] in legal
        seen.add(res["from_sq"] + res["to_sq"])
    assert len(seen) >= 1
