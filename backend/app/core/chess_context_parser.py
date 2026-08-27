"""棋局状态解析模块（自研核心 1/5）★

职责：把象棋引擎的原始输出（FEN / 落子 / 评估）转为标准化结构化博弈上下文 JSON，
供 Prompt 组装器 / 记忆管理器使用。强制约束：不直接把原始 FEN 传给大模型。

对齐 spec 2.1「棋局状态解析模块」、2.3「禁止直接传入原始 FEN」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# 中国象棋棋盘：9 列(0..8, file) x 10 行(0..9, rank)，红方在下
COLS = "abcdefghi"
FILES = list(COLS)
RANKS = list(range(10))

# 棋子记号：大写=红方(下)、小写=黑方(上)，与 ryoi/xiangqi 引擎约定一致
PIECE_NAMES = {
    "K": "帅", "A": "仕", "B": "相", "N": "马", "R": "车", "C": "炮", "P": "兵",  # 红方
    "k": "将", "a": "士", "b": "象", "n": "马", "r": "车", "c": "炮", "p": "卒",  # 黑方
}


@dataclass
class Move:
    """一着棋：源 / 目标 / 棋子 / 是否吃子 / 被吃棋子。"""
    from_sq: str
    to_sq: str
    piece: str
    captured: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "from": self.from_sq,
            "to": self.to_sq,
            "piece": self.piece,
            "piece_name": PIECE_NAMES.get(self.piece, self.piece),
        }
        if self.captured:
            d["captured"] = self.captured
            d["captured_name"] = PIECE_NAMES.get(self.captured, self.captured)
        return d


def parse_fen(fen: str) -> list[Optional[str]]:
    """FEN 棋盘部分 -> 64 格(黑方 9x10 视角)列表，空位为 None。

    中国象棋 FEN 首位为黑方(上方)视角，共 10 行。
    """
    board_part = fen.split(" ")[0]
    ranks = board_part.split("/")
    assert len(ranks) == 10, f"中国象棋 FEN 应为 10 行，实际 {len(ranks)}"
    cells: list[Optional[str]] = []
    for rank in ranks:
        for ch in rank:
            if ch.isdigit():
                cells.extend([None] * int(ch))
            else:
                cells.append(ch)
    return cells


def fen_to_board(fen: str) -> list[list[Optional[str]]]:
    """FEN -> 9x10 矩阵 board[rank][file]，rank=0 为黑方底线（上方）。"""
    cells = parse_fen(fen)
    return [cells[r * 9 : (r + 1) * 9] for r in range(10)]


def sq_to_index(sq: str) -> int:
    """'a0'..'i9' -> 0..89 索引（与 parse_fen 顺序一致，rank0=黑方）。"""
    m = re.fullmatch(r"([a-i])([0-9])", sq)
    if not m:
        raise ValueError(f"非法坐标: {sq!r}（需 a0..i9）")
    f, r = m.group(1), int(m.group(2))
    return r * 9 + FILES.index(f)


def index_to_sq(idx: int) -> str:
    return f"{FILES[idx % 9]}{idx // 9}"


def detect_move(prev_fen: str, new_fen: str) -> Move:
    """对比相邻两局面，还原一着棋（含吃子）。

    说明：仅按棋盘差异推断，作为无引擎环境的结构化入口；
    接入 ryoi/xiangqi 的 logic.js 后由引擎直接上报 from/to 与本方法互补验证。
    """
    a = parse_fen(prev_fen)
    b = parse_fen(new_fen)
    moved_from = moved_to = None
    captured = None
    for i, (pa, pb) in enumerate(zip(a, b)):
        if pa != pb:
            if pa is not None and pb is None:
                moved_from = i
            elif pa is None and pb is not None:
                moved_to = i
            elif pa is not None and pb is not None:
                # 吃子：目标格发生替换
                moved_to = i
                captured = pa
    if moved_from is None or moved_to is None:
        raise ValueError("无法从相邻 FEN 推断落子，请核对输入")
    piece = a[moved_from]
    return Move(
        from_sq=index_to_sq(moved_from),
        to_sq=index_to_sq(moved_to),
        piece=piece,
        captured=captured,
    )


def count_material(board: list[list[Optional[str]]]) -> dict[str, int]:
    """双方剩余子力统计（按棋子种类）。"""
    material: dict[str, int] = {}
    for row in board:
        for p in row:
            if p:
                material[p] = material.get(p, 0) + 1
    return material


def side_to_move(fen: str) -> str:
    """FEN 第二个字段：w=红先，b=黑先。"""
    parts = fen.split(" ")
    return parts[1] if len(parts) > 1 else "w"


def is_check(fen: str) -> bool:
    """通过 FEN 第 4 段（王被将军标记）粗判将军；无标记时返回 False。

    精确判定需引擎；这里保证输出字段结构稳定，接入引擎后替换。
    """
    parts = fen.split(" ")
    return len(parts) > 3 and parts[3] == "-"


def build_context(
    *,
    user_move: Optional[Move] = None,
    ai_move: Optional[Move] = None,
    fen: str,
    evaluation: Optional[float] = None,
    win_probability: Optional[float] = None,
    events: Optional[list[str]] = None,
) -> dict:
    """标准化博弈上下文 JSON（供 Prompt 使用的可读结构）。"""
    board = fen_to_board(fen)
    material = count_material(board)
    ctx = {
        "fen": fen,  # 存档用；Prompt 组装器会将其剥离
        "side_to_move": side_to_move(fen),
        "material": material,
        "material_text": material_text(material),
        "in_check": is_check(fen),
        "events": events or [],
        "user_move": user_move.to_dict() if user_move else None,
        "ai_move": ai_move.to_dict() if ai_move else None,
        "evaluation": evaluation,
        "win_probability": win_probability,
    }
    return ctx


def material_text(material: dict[str, int]) -> str:
    """子力统计 -> 可读文本（供大模型理解局面）。大写=红方、小写=黑方。"""
    red = [f"{PIECE_NAMES[p]}{n}" for p, n in sorted(material.items()) if p.isupper()]
    black = [f"{PIECE_NAMES[p]}{n}" for p, n in sorted(material.items()) if p.islower()]
    return f"红方: {'、'.join(red) or '无'}; 黑方: {'、'.join(black) or '无'}"


def apply_move_to_fen(fen: str, from_sq: str, to_sq: str) -> str:
    """在 FEN 上应用一着棋，返回新 FEN（棋盘部分重建，其余字段原样保留）。

    注意：本工具只移动棋子、不做合法性校验（走法校验由象棋引擎负责），
    主要用于测试与棋谱回放。
    """
    cells = parse_fen(fen)
    fi, ti = sq_to_index(from_sq), sq_to_index(to_sq)
    if cells[fi] is None:
        raise ValueError(f"源格 {from_sq} 无棋子")
    cells[ti] = cells[fi]
    cells[fi] = None
    ranks: list[str] = []
    for r in range(10):
        chunk = cells[r * 9 : (r + 1) * 9]
        row = ""
        empty = 0
        for p in chunk:
            if p is None:
                empty += 1
            else:
                if empty:
                    row += str(empty)
                    empty = 0
                row += p
        if empty:
            row += str(empty)
        ranks.append(row)
    parts = fen.split(" ")
    parts[0] = "/".join(ranks)
    return " ".join(parts)


def make_default_fen() -> str:
    """初始局面 FEN（黑方视角，红先）。"""
    return "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
