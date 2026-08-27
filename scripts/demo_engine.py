"""演示脚本：走 3 手棋，展示引擎 AI 应手、事件、胜率、LLM 台词。

用法：cd os2026_chess_friend && python scripts/demo_engine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 仓库根目录

from fastapi.testclient import TestClient

from backend.app.core import chess_context_parser as ccp
from backend.app.main import app


def main() -> None:
    client = TestClient(app)
    g = client.post("/api/games", json={"user_id": "engine-demo", "personality": "laozhang"}).json()
    fen = g["fen"]
    print("开局 FEN:", fen)
    print("数字人开关:", g["digital_human_enabled"])
    print()

    for i, (fs, ts) in enumerate([("a6", "a5"), ("c6", "c5"), ("e6", "e5")], 1):
        new_fen = ccp.apply_move_to_fen(fen, fs, ts)
        body = client.post(
            "/api/moves",
            json={"game_id": g["game_id"], "user_id": "engine-demo", "fen": new_fen, "from_sq": fs, "to_sq": ts},
        ).json()
        ai = body["ai_move"]
        f, t, piece = ai["from_sq"], ai["to_sq"], ai["piece"]
        print(f"回合{i}: 玩家 {fs}->{ts}")
        print(f"   AI 应手: {f}->{t} ({piece}) | 玩家胜率 {ai['win_probability']:.0%}" if ai.get("win_probability") is not None else f"   AI 应手: {f}->{t} ({piece})")
        print(f"   事件: {body['events'] or '无'}")
        print(f"   老张: {body['llm_output']['speech_text']}  [{body['llm_output']['emotion_tag']}]")
        print()
        fen = body["new_fen"]


if __name__ == "__main__":
    main()
