"""象棋引擎适配层：subprocess 调 Node 运行 ryoi/xiangqi 的 logic.js。

自研粘合层：FEN <-> 引擎棋盘转换、AI 应手、局面评估、将军/将死/困毙判定。
引擎文件来自 https://github.com/ryoi/xiangqi（MIT），以 vendor 方式内置并标注归属。
"""
from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)

_HOST = Path(__file__).parent / "js" / "engine_host.js"
_DEFAULT_LOGIC = Path(__file__).resolve().parents[2] / "vendor" / "xiangqi" / "logic.js"


class EngineError(RuntimeError):
    """引擎调用/解析失败。"""


def _logic_path() -> Path:
    settings = get_settings()
    p = Path(settings.engine_logic_path) if settings.engine_logic_path else _DEFAULT_LOGIC
    if not p.exists():
        raise FileNotFoundError(f"象棋引擎 logic.js 不存在: {p}（可设置 ENGINE_LOGIC_PATH 指定路径）")
    return p


def _node_bin() -> str:
    node = shutil.which("node")
    if not node:
        raise EngineError("未找到 node 运行时，请安装 Node.js（引擎通过 node 执行 logic.js）")
    return node


def _run(action: str, payload: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    """执行一次引擎指令，返回解析后的 JSON。"""
    data: dict[str, Any] = {"action": action, **payload}
    proc = subprocess.run(
        [_node_bin(), str(_HOST), str(_logic_path())],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise EngineError(f"node 引擎退出码 {proc.returncode}: {proc.stderr[:300]}")
    out = proc.stdout.strip()
    if not out:
        raise EngineError("node 引擎无输出")
    try:
        obj = json.loads(out)
    except json.JSONDecodeError:
        raise EngineError(f"引擎输出非 JSON: {out[:200]}")
    if not obj.get("ok"):
        raise EngineError(obj.get("error", "引擎返回错误"))
    return obj


def score_to_win_prob(score: float, scale: float = 250.0) -> float:
    """评估分 -> 胜率（对持有该评估分的行动方）。sigmoid。"""
    return 1.0 / (1.0 + math.exp(-score / scale))


def ping() -> bool:
    return bool(_run("ping", {}).get("pong"))


def position_status(fen: str, color: str = "red") -> dict[str, Any]:
    """局面状态：将军 / 将死 / 困毙 / 合法着法数 / 评估分。"""
    return _run("position", {"fen": fen, "color": color})


def ai_move(
    fen: str,
    color: str = "black",
    difficulty: Optional[int] = None,
    time_ms: Optional[int] = None,
    move_number: Optional[int] = None,
    use_opening_book: bool = True,
) -> dict[str, Any]:
    """让引擎为指定方计算一手棋。

    返回：{from_sq, to_sq, piece, new_fen, score, win_probability, ...}
    """
    settings = get_settings()
    diff = difficulty or settings.engine_skill
    tms = time_ms if time_ms is not None else (settings.engine_time_ms or None)
    res = _run(
        "ai_move",
        {
            "fen": fen,
            "color": color,
            "difficulty": diff,
            "timeMs": tms,
            "moveNumber": move_number,
            "useOpeningBook": use_opening_book,
        },
    )
    mv = res.get("move")
    if not mv:
        return {
            "from_sq": None,
            "to_sq": None,
            "piece": None,
            "new_fen": fen,
            "score": None,
            "win_probability": None,
            "reason": res.get("reason", "no-legal-move"),
        }
    from_sq, to_sq = mv["from"], mv["to"]
    new_fen = res["newFen"]
    # 用本仓库 parser 还原被移动的棋子（FEN 对比）
    from .chess_context_parser import detect_move

    piece = None
    try:
        piece = detect_move(fen, new_fen).piece
    except Exception:
        piece = None
    score = res.get("score")
    return {
        "from_sq": from_sq,
        "to_sq": to_sq,
        "piece": piece,
        "new_fen": new_fen,
        "score": score,
        "win_probability": score_to_win_prob(score) if score is not None else None,
        "opponent_in_check": res.get("opponent_in_check"),
        "opponent_checkmate": res.get("opponent_checkmate"),
        "opponent_stalemate": res.get("opponent_stalemate"),
    }
