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


def test_opening_book_black_reply_to_central_cannon(engine_ready):
    """开局棋谱坐标修正：红当头炮(炮二平五)后，黑方应着必须含标准 屏风马(h0->g2)
    与 顺手炮(h2->e2)，且修复前那种往边角的怪跳(b0->a2)不再出现。"""
    after_red = ccp.toggle_side(ccp.apply_move_to_fen(DEFAULT_FEN, "b7", "e7"))  # 红 炮二平五
    legal = _legal_from_to(after_red, "black")
    seen = set()
    for _ in range(40):
        res = ai_move(after_red, color="black", difficulty=2, move_number=1, diversity=True)
        assert res["from_sq"] and res["to_sq"]
        mv = res["from_sq"] + res["to_sq"]
        assert mv in legal
        seen.add(mv)
    assert "h0g2" in seen, "当头炮后应能走出标准屏风马(马8进7 护中)"
    assert "h2e2" in seen, "当头炮后应能走出顺手炮(炮8平5)——修复前坐标错误导致永远不出现"
    assert "b0a2" not in seen, "修复前把屏风马误写成往边角跳(b0->a2)不应再出现"


def test_target_win_prob_keeps_moves_legal(engine_ready):
    """动态胜率控制：targetUserWinProb 不破坏合法性/不崩。"""
    fen = ccp.apply_move_to_fen(DEFAULT_FEN, "a6", "a5")
    legal = _legal_from_to(fen, "black")
    for _ in range(12):
        res = ai_move(fen, color="black", difficulty=3, move_number=2, diversity=True, target_user_win_prob=0.5)
        assert res["from_sq"] and res["to_sq"]
        assert res["from_sq"] + res["to_sq"] in legal


def test_target_win_prob_biases_selection(engine_ready):
    """动态胜率控制：目标越偏向用户（0.99=让用户赢），选着平均评估分越低
    （AI 主动走弱一点）；目标越偏向 AI（0.01），选着平均评估分越高。
    用「黑车可免费吃红车」的战术局面放大分差（该局面着法分确定：吃=109 / 开发=29 / 其余=-1）。"""
    fen = "r4k3/9/9/9/R8/9/9/9/9/4K4 b - - 0 1"
    assert "a0a4" in {m["from"] + m["to"] for m in legal_moves(fen, "black")}
    scores_high = []  # target=0.99（AI 放水，让用户赢）
    scores_low = []   # target=0.01（AI 求最优，压用户）
    for _ in range(40):
        r_high = ai_move(fen, color="black", difficulty=3, move_number=8, diversity=True, target_user_win_prob=0.99)
        r_low = ai_move(fen, color="black", difficulty=3, move_number=8, diversity=True, target_user_win_prob=0.01)
        assert r_high["score"] is not None and r_low["score"] is not None
        scores_high.append(r_high["score"])
        scores_low.append(r_low["score"])
    avg_high = sum(scores_high) / len(scores_high)
    avg_low = sum(scores_low) / len(scores_low)
    assert avg_high < avg_low, f"放水模式平均分应更低: high={avg_high:.1f} low={avg_low:.1f}"
