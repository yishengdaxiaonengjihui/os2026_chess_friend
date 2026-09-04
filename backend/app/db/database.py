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
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                nickname TEXT NOT NULL,
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
                starred INTEGER DEFAULT 0,
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
        # 迁移：为老库补 starred 列（幂等）
        cols = [c[1] for c in cur.execute("PRAGMA table_info(games)").fetchall()]
        if cols and "starred" not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN starred INTEGER DEFAULT 0")
        # 迁移：为老库补 users.chat_pref 列（问题12 闲聊三档偏好，幂等）
        ucols = [c[1] for c in cur.execute("PRAGMA table_info(users)").fetchall()]
        if ucols and "chat_pref" not in ucols:
            cur.execute("ALTER TABLE users ADD COLUMN chat_pref TEXT DEFAULT 'balanced'")
        conn.commit()
    finally:
        conn.close()


# ---------------- 用户管理 ----------------

def create_user(nickname: str) -> dict:
    """创建账号：昵称去重（同昵称复用已有账号），返回用户记录。"""
    import uuid

    conn = get_conn()
    try:
        row = conn.execute("SELECT user_id, nickname, created_at FROM users WHERE nickname=?", (nickname,)).fetchone()
        if row:
            return {"user_id": row[0], "nickname": row[1], "created_at": row[2], "created": False}
        uid = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("INSERT INTO users (user_id, nickname, created_at) VALUES (?,?,?)", (uid, nickname, now))
        conn.commit()
        return {"user_id": uid, "nickname": nickname, "created_at": now, "created": True}
    finally:
        conn.close()


def get_user(user_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT user_id, nickname, created_at, chat_pref FROM users WHERE user_id=?", (user_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"user_id": row[0], "nickname": row[1], "created_at": row[2], "chat_pref": row[3] or "balanced"}


def set_chat_pref(user_id: str, pref: str) -> dict:
    """问题12：设置用户闲聊偏好（quiet / balanced / chatty）。"""
    if pref not in ("quiet", "balanced", "chatty"):
        raise ValueError("闲聊偏好取值必须为 quiet / balanced / chatty")
    conn = get_conn()
    try:
        cur = conn.execute("UPDATE users SET chat_pref=? WHERE user_id=?", (pref, user_id))
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise ValueError("账号不存在")
    u = get_user(user_id)
    assert u is not None
    return u


def list_users() -> list[dict]:
    """所有账号（含各自对局数，新的在前）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT u.user_id, u.nickname, u.created_at, COUNT(g.game_id) AS n "
            "FROM users u LEFT JOIN games g ON g.user_id = u.user_id "
            "GROUP BY u.user_id ORDER BY u.created_at ASC"
        ).fetchall()
    finally:
        conn.close()
    return [
        {"user_id": r[0], "nickname": r[1], "created_at": r[2], "games_count": r[3] or 0}
        for r in rows
    ]


def rename_user(user_id: str, nickname: str) -> dict:
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET nickname=? WHERE user_id=?", (nickname, user_id))
        conn.commit()
    finally:
        conn.close()
    u = get_user(user_id)
    if not u:
        raise ValueError("账号不存在")
    return u


def delete_user(user_id: str) -> None:
    """删除账号及全部数据（画像/长期记忆/棋谱/棋谱着法）。"""
    conn = get_conn()
    try:
        game_ids = [r[0] for r in conn.execute("SELECT game_id FROM games WHERE user_id=?", (user_id,)).fetchall()]
        for gid in game_ids:
            conn.execute("DELETE FROM game_moves WHERE game_id=?", (gid,))
        conn.execute("DELETE FROM games WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM long_term_memories WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------- 棋谱：加精 / 删除 ----------------

def set_game_starred(game_id: str, starred: bool) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE games SET starred=? WHERE game_id=?", (1 if starred else 0, game_id))
        conn.commit()
    finally:
        conn.close()


def delete_game_record(game_id: str) -> None:
    """删除整局棋谱（含着法记录）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM game_moves WHERE game_id=?", (game_id,))
        conn.execute("DELETE FROM games WHERE game_id=?", (game_id,))
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


def list_games(user_id: str, limit: int = 200) -> list[dict]:
    """棋谱库：按用户列出对局（新的在前），含四状态与加精标记。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT game_id, user_id, move_count, result, starred, created_at, finished_at "
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
            "starred": bool(r[4]),
            "created_at": r[5],
            "finished_at": r[6],
        }
        for r in rows
    ]


def get_game_start_fen(game_id: str) -> str | None:
    """棋谱回放：取该对局的开局 FEN。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT start_fen FROM games WHERE game_id=?", (game_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


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
