"""SQLite 数据库初始化与通用访问。

对齐 spec 2.1 存储层：
- 会话快照、对局元数据、结构化用户画像、棋谱原始记录
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

from ..config import get_settings


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    settings = get_settings()
    path = db_path or settings.sqlite_path
    _ensure_dir(path)
    return sqlite3.connect(path)


def init_db(db_path: str | None = None) -> None:
    """建表（幂等）。"""
    conn = get_conn(db_path)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                personality TEXT DEFAULT 'laozhang',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                start_fen TEXT NOT NULL,
                final_fen TEXT,
                result TEXT,
                move_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS game_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                move_index INTEGER NOT NULL,
                user_move TEXT,
                ai_move TEXT,
                fen TEXT NOT NULL,
                events TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                short_term_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS long_term_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_game_record(game_id: str, session_id: str, user_id: str, start_fen: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO games (game_id, session_id, user_id, start_fen, created_at) VALUES (?,?,?,?,?)",
            (game_id, session_id, user_id, start_fen, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def append_move_record(game_id: str, move_index: int, user_move, ai_move, fen: str, events: list[str]) -> None:
    import json

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO game_moves (game_id, move_index, user_move, ai_move, fen, events, created_at) VALUES (?,?,?,?,?,?,?)",
            (game_id, move_index, json.dumps(user_move, ensure_ascii=False) if user_move else None, json.dumps(ai_move, ensure_ascii=False) if ai_move else None, fen, json.dumps(events, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
        conn.execute("UPDATE games SET move_count = move_count + 1 WHERE game_id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()


def finish_game_record(game_id: str, result: str, final_fen: str) -> None:
    """对局结束：写入结果与终局 FEN。result: 'win'|'lose'|'draw'（用户视角）。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE games SET result=?, final_fen=?, finished_at=? WHERE game_id=?",
            (result, final_fen, datetime.now().isoformat(timespec="seconds"), game_id),
        )
        conn.commit()
    finally:
        conn.close()


def remove_last_move_record(game_id: str) -> None:
    """悔棋：删除该对局最后一轮着法记录。"""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM game_moves WHERE game_id=? AND id = "
            "(SELECT MAX(id) FROM game_moves WHERE game_id=?)",
            (game_id, game_id),
        )
        conn.commit()
    finally:
        conn.close()


def clear_game_result(game_id: str) -> None:
    """悔棋：清掉已写入的终局结果（对局回到未结束状态）。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE games SET result=NULL, final_fen=NULL, finished_at=NULL WHERE game_id=?",
            (game_id,),
        )
        conn.commit()
    finally:
        conn.close()


def decrement_move_count(game_id: str, n: int = 1) -> None:
    """悔棋：对局手数回退。"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE games SET move_count = MAX(move_count - ?, 0) WHERE game_id=?",
            (n, game_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_games(user_id: str, limit: int = 50) -> list[dict]:
    """棋谱库：按用户列出对局（新的在前）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT game_id, user_id, move_count, result, created_at, finished_at "
            "FROM games WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "game_id": r[0],
            "user_id": r[1],
            "move_count": r[2] or 0,
            "result": r[3],
            "created_at": r[4],
            "finished_at": r[5],
        }
        for r in rows
    ]


def get_game_moves(game_id: str) -> list[dict]:
    """棋谱：返回某对局的逐手记录（含双方着法与事件）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT move_index, user_move, ai_move, fen, events FROM game_moves "
            "WHERE game_id=? ORDER BY move_index ASC",
            (game_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "move_index": r[0],
            "user_move": json.loads(r[1]) if r[1] else None,
            "ai_move": json.loads(r[2]) if r[2] else None,
            "fen": r[3],
            "events": json.loads(r[4]) if r[4] else [],
        }
        for r in rows
    ]
