"""分层记忆管理器（自研核心 2/5）★

对齐 spec 2.1「记忆管理器」三层结构：
1. 短期会话记忆：内存维护本局对话，新对局清空，定期快照落盘 SQLite
2. 长期记忆适配器：封装 Mem0 SDK（底层 Chroma）；未安装 mem0 时降级为 SQLite 摘要存储，保证无网/轻量可跑
3. 结构化画像读写：SQLite 维护棋风/棋力/闲聊偏好，不归 mem0 管理
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..config import get_settings


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str
    ts: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ShortTermMemory:
    """本局短期会话记忆：内存环形列表，新对局清空。"""

    def __init__(self, max_turns: Optional[int] = None):
        settings = get_settings()
        self.max_turns = max_turns or settings.short_term_max_turns
        self.turns: list[Turn] = []

    def add(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def replace_last_user(self, content: str) -> None:
        """问题3：连续消息只响应最新 —— 覆盖/去重最后一条用户输入，
        避免同一时刻的重复语音/连续消息污染对话上下文。"""
        for i in range(len(self.turns) - 1, -1, -1):
            if self.turns[i].role == "user":
                self.turns[i].content = content
                return
        self.add("user", content)

    def to_openai_messages(self) -> list[dict]:
        return [{"role": t.role, "content": t.content} for t in self.turns]

    def clear(self) -> None:
        self.turns.clear()

    def as_text(self) -> str:
        return "\n".join(f"{t.role}: {t.content}" for t in self.turns)


class LongTermMemory:
    """长期记忆适配器。

    优先使用 Mem0 SDK（若已安装且配置了 API Key）；否则降级为
    SQLite 摘要库 + 简单关键词召回，保证第一阶段无需大依赖即可跑通。
    接口保持一致：add() / search()。
    """

    def __init__(self, user_id: str, db_path: Optional[str] = None):
        settings = get_settings()
        self.user_id = user_id
        self.db_path = db_path or settings.sqlite_path
        self._mem0 = None
        try:
            from mem0 import Memory  # type: ignore

            config = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {"collection_name": f"mem_{user_id}", "path": settings.chroma_dir},
                },
            }
            self._mem0 = Memory.from_config(config)
        except Exception:
            self._mem0 = None  # 降级 SQLite
        self._init_sqlite()

    # ---- 底层 ----
    def _conn(self) -> sqlite3.Connection:
        import os

        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init_sqlite(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS long_term_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )"""
            )

    # ---- 对外接口 ----
    def add(self, content: str, metadata: Optional[dict] = None) -> None:
        if self._mem0 is not None:
            self._mem0.add(content, user_id=self.user_id, metadata=metadata or {})
            return
        with self._conn() as c:
            c.execute(
                "INSERT INTO long_term_memories (user_id, content, metadata, created_at) VALUES (?,?,?,?)",
                (self.user_id, content, json.dumps(metadata or {}, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
            )

    def search(self, query: str, top_k: Optional[int] = None) -> list[str]:
        settings = get_settings()
        top_k = top_k or settings.long_term_recall_top_k
        if self._mem0 is not None:
            results = self._mem0.search(query, user_id=self.user_id, limit=top_k)
            return [str(r.get("memory", r)) for r in results]
        # 降级：按查询词子串匹配召回（中文无需分词，子串命中即计分）
        qterms = [t for t in query.replace("。", " ").replace("，", " ").split() if t]
        with self._conn() as c:
            rows = c.execute(
                "SELECT content FROM long_term_memories WHERE user_id=? ORDER BY id DESC",
                (self.user_id,),
            ).fetchall()
        scored = []
        for (content,) in rows:
            text = str(content)
            if not qterms:
                scored.append((0, text))
                continue
            score = sum(1 for t in qterms if t in text)
            if score > 0:
                scored.append((score, text))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k]]


class ProfileStore:
    """SQLite 结构化用户画像读写（强结构化字段不归 mem0 管理）。"""

    DEFAULT_PROFILE = {
        "nickname": "棋友",
        "style": "未知（待对局观察）",
        "strength": "未知",
        "preferences": "",
        "opening": "",
        "notes": "",
    }

    def __init__(self, db_path: Optional[str] = None):
        settings = get_settings()
        self.db_path = db_path or settings.sqlite_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        import os

        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )

    def get(self, user_id: str) -> dict[str, Any]:
        with self._conn() as c:
            row = c.execute("SELECT profile FROM profiles WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return dict(self.DEFAULT_PROFILE)
        return json.loads(row[0])

    def merge_diff(self, user_id: str, diff: dict[str, Any]) -> dict[str, Any]:
        """合并画像 diff（只更新变更字段，不覆盖全部画像）。"""
        cur = self.get(user_id)
        cur.update({k: v for k, v in diff.items() if v not in (None, "", [])})
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO profiles (user_id, profile, updated_at) VALUES (?,?,?)",
                (user_id, json.dumps(cur, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
            )
        return cur

    def reset(self, user_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))


# 问题9：长期记忆写入管控 —— 只有「整局摘要」与「用户主动透露个人信息」两个场景写 Mem0。
# 对局中的临时点评只进本局短期内存。这里做个人信息轻量识别。
_PERSONAL_KEYWORDS = [
    "我今年", "我退休", "我老伴", "我孙子", "我孙女", "我儿子", "我女儿", "我孩子",
    "我喜欢", "我爱", "我平时", "我习惯", "我身体", "我膝盖", "我血压",
    "我睡不着", "我心情", "我最近", "我们家", "我叫", "我是",
]


def detect_personal_info(text: str) -> Optional[str]:
    """识别用户主动透露的个人生活 / 爱好 / 情绪信息；命中返回规范化记忆文本，否则 None。"""
    if not text:
        return None
    for kw in _PERSONAL_KEYWORDS:
        if kw in text:
            return f"用户主动提及：{text.strip()[:60]}"
    return None


class MemoryManager:
    """对外总入口：把三层记忆统一暴露给编排层。"""

    def __init__(self, user_id: str, game_id: str):
        self.user_id = user_id
        self.game_id = game_id
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory(user_id)
        self.profile_store = ProfileStore()

    def recall(self, query: str) -> dict:
        """一次召回：短期历史 + 长期记忆 + 结构化画像。"""
        return {
            "short_term": self.short_term.to_openai_messages(),
            "long_term": self.long_term.search(query),
            "profile": self.profile_store.get(self.user_id),
        }

    def remember_turn(self, role: str, content: str) -> None:
        self.short_term.add(role, content)

    def end_game(self) -> None:
        """对局结束：清空短期会话记忆，保留长期记忆与画像。"""
        self.short_term.clear()
