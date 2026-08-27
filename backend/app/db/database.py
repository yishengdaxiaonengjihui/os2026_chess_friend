"""SQLite 数据库初始化与通用访问。

对齐 spec 2.1 存储层：
- 会话快照、对局元数据、结构化用户画像、棋谱原始记录
"""
from __future__ import annotations

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
