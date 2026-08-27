"""结构化用户画像读写（SQLite）。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from .database import get_conn

DEFAULT_PROFILE: dict[str, Any] = {
    "nickname": "棋友",
    "style": "未知（待对局观察）",
    "strength": "未知",
    "preferences": "",
    "opening": "",
    "notes": "",
}


def get_profile(user_id: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT profile FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return dict(DEFAULT_PROFILE)
    return json.loads(row[0])


def merge_profile_diff(user_id: str, diff: dict[str, Any]) -> dict[str, Any]:
    """合并画像 diff：只更新非空变更字段，不覆盖全部画像。"""
    cur = get_profile(user_id)
    cur.update({k: v for k, v in diff.items() if v not in (None, "", [], {})})
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO profiles (user_id, profile, updated_at) VALUES (?,?,?)",
            (user_id, json.dumps(cur, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return cur


def reset_profile(user_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()
