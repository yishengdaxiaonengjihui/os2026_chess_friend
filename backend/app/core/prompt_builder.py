"""五层 Prompt 组装器（自研核心 3/5）★

对齐 spec 2.3 五层结构：
1. 系统角色设定（固定 System Prompt，约束输出 JSON，限定情绪/动作枚举）
2. SQLite 结构化用户画像
3. Mem0 召回得到的长期记忆摘要
4. 棋局解析模块输出的结构化棋局局势信息
5. 本局短期会话对话历史

强制约束：禁止把原始 FEN 直接传入大模型。
"""
from __future__ import annotations

import json
from typing import Any, Optional

EMOTIONS = ["平静", "喜悦", "惋惜", "惊讶", "赞赏", "鼓励", "沉思", "得意"]
ACTIONS = ["nod", "smile", "frown", "applaud", "lean", "wave", "shrug", "idle"]

SYSTEM_ROLE = (
    "你是「老张」——一位住在社区棋摊旁的退休象棋老手，性格爽朗、爱下棋也爱唠嗑，"
    "现在作为独居老人李大爷的专属数字人象棋棋友陪他下棋。"
    "你既是合格的棋手，也是能给棋友带来陪伴感的老朋友。\n"
    "硬性要求：\n"
    f"1. 每次回复只输出一个 JSON 对象，不要输出任何其他文字。\n"
    "2. 必须结合传入的棋局局势信息说话，内容要贴合当下棋局，禁止完全脱离棋局闲聊。\n"
    "3. 台词用口语化的中文，简短（不超过 40 字），像棋友在耳边说话。\n"
    "4. emotion_tag 只能取以下枚举之一：" + "、".join(EMOTIONS) + "。\n"
    "5. action_tag 只能取以下枚举之一：" + "、".join(ACTIONS) + "。\n"
    '6. 输出 JSON 结构严格为 {"speech_text": "...", "emotion_tag": "...", "action_tag": "..."}。'
)


def _profile_to_text(profile: dict[str, Any]) -> str:
    if not profile:
        return "（暂无画像数据）"
    lines = []
    stats = profile.get("stats")
    for k, v in profile.items():
        if not v:
            continue
        if k == "stats":
            lines.append("- 历史战绩: " + _stats_to_text(stats))
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines) or "（暂无画像数据）"


def _stats_to_text(stats: dict) -> str:
    if not stats:
        return "（暂无对局记录）"
    return (
        f"共{stats.get('games', 0)}局，胜{stats.get('wins', 0)}负{stats.get('losses', 0)}"
        f"平{stats.get('draws', 0)}，累计{stats.get('moves', 0)}手，吃子{stats.get('user_captures', 0)}枚"
    )


def _board_to_text(ctx: dict[str, Any]) -> str:
    """把结构化博弈上下文转成可读文本（刻意剥离原始 FEN）。"""
    lines = []
    if ctx.get("user_move"):
        m = ctx["user_move"]
        lines.append(f"玩家刚刚：{m['piece_name']}从{m['from']}走到{m['to']}" + (f"，吃掉对方{m['captured_name']}" if m.get("captured_name") else ""))
    if ctx.get("ai_move"):
        m = ctx["ai_move"]
        lines.append(f"你应了一手：{m['piece_name']}从{m['from']}走到{m['to']}" + (f"，吃掉对方{m['captured_name']}" if m.get("captured_name") else ""))
    if ctx.get("material_text"):
        lines.append("当前子力：" + ctx["material_text"])
    if ctx.get("events"):
        lines.append("本回合事件：" + "、".join(ctx["events"]))
    if ctx.get("in_check"):
        lines.append("注意：当前处于将军状态。")
    if ctx.get("win_probability") is not None:
        lines.append(f"胜率预估：玩家 {ctx['win_probability']:.0%}")
    return "\n".join(lines) if lines else "（开局阶段）"


def build_prompt(
    *,
    profile: Optional[dict[str, Any]] = None,
    long_term_memories: Optional[list[str]] = None,
    board_context: Optional[dict[str, Any]] = None,
    short_term_history: Optional[list[dict]] = None,
    system_role: Optional[str] = None,
) -> list[dict]:
    """拼装五层 Prompt，返回 OpenAI messages 列表。"""
    layers: list[tuple[str, str]] = [
        ("【第2层 棋友画像】", _profile_to_text(profile or {})),
        ("【第3层 你们之前聊过的事】", "\n".join(f"- {m}" for m in (long_term_memories or [])) or "（暂无长期记忆）"),
        ("【第4层 当前棋局局势】", _board_to_text(board_context or {})),
        ("【第5层 本局对话历史】", ""),
    ]

    system = system_role or SYSTEM_ROLE
    for title, body in layers[:3]:
        system += f"\n\n{title}\n{body}"

    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(short_term_history or [])
    # 附上一份近期对话（第5层）以确保历史不被裁剪丢失
    if messages and messages[-1]["role"] == "user":
        messages.append({"role": "user", "content": "（请你基于以上所有信息，结合当前棋局，用老张的口吻说一句话。）"})
    return messages


def json_schema_instruction() -> str:
    """供 LLM 客户端使用的输出约束说明（与 system prompt 一致）。"""
    return json.dumps(
        {"speech_text": "string", "emotion_tag": "enum(" + "/".join(EMOTIONS) + ")", "action_tag": "enum(" + "/".join(ACTIONS) + ")"},
        ensure_ascii=False,
    )
