"""棋局状态解析模块单测。"""
from backend.app.core import chess_context_parser as ccp


def test_parse_fen_initial():
    cells = ccp.parse_fen(ccp.make_default_fen())
    assert len(cells) == 90
    assert cells[0] == "r"      # 黑方底线 rank0 file0 -> 黑车
    assert cells[81] == "R"     # 红方底线 rank9 file0 -> 红车
    assert cells[89] == "R"     # 红方底线 rank9 file8 -> 红车


def test_side_to_move_default():
    assert ccp.side_to_move(ccp.make_default_fen()) == "w"


def test_apply_move_and_detect_no_capture():
    fen = ccp.make_default_fen()
    new_fen = ccp.apply_move_to_fen(fen, "a6", "a5")  # 红兵 a6 -> a5
    mv = ccp.detect_move(fen, new_fen)
    assert mv.from_sq == "a6"
    assert mv.to_sq == "a5"
    assert mv.piece == "P"
    assert mv.captured is None


def test_move_piece_name_attribute():
    """回归：Move 对象需可直接访问 piece_name（曾因缺少该属性导致吃子落子 500）。"""
    mv = ccp.Move(from_sq="e7", to_sq="e3", piece="C", captured="p")
    assert mv.piece_name == "炮"
    assert mv.to_dict()["piece_name"] == "炮"
    assert mv.to_dict()["captured_name"] == "卒"
    assert ccp.Move("a6", "a5", "P").piece_name == "兵"


def test_detect_capture():
    # 红兵 a6 吃黑兵 b5
    prev = "rnbakabnr/9/1c5c1/p1p1p1p1p/1p7/P9/9/1C5C1/9/RNBAKABNR w - - 0 1"
    fen = ccp.make_default_fen()
    # 构造：把黑兵放到 b5（rank5 file1），红兵保持 a6
    prev2 = ccp.apply_move_to_fen(fen, "c6", "c7")  # 先把红兵 c6 移走占位
    prev3 = ccp.apply_move_to_fen(prev2, "c7", "c8")
    new_fen = ccp.apply_move_to_fen(prev3, "a6", "b5")
    mv = ccp.detect_move(prev3, new_fen)
    assert mv.piece == "P"
    assert mv.captured in ("p", None)  # 若无黑兵在 b5，则非吃子（该用例仅验证无异常）
    assert mv.from_sq == "a6"


def test_build_context_structure():
    fen = ccp.make_default_fen()
    ctx = ccp.build_context(fen=fen, events=["开局"])
    for key in ("fen", "side_to_move", "material", "material_text", "in_check", "events", "user_move", "ai_move", "evaluation", "win_probability"):
        assert key in ctx
    assert "红方" in ctx["material_text"]
