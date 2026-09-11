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

from .persona_store import persona_for, story_prompt_block

EMOTIONS = ["平静", "喜悦", "惋惜", "惊讶", "赞赏", "鼓励", "沉思", "得意"]
ACTIONS = ["nod", "smile", "frown", "applaud", "lean", "wave", "shrug", "idle"]

_HARD_REQS = (
    "\n硬性要求：\n"
    "1. 每次回复只输出一个 JSON 对象，不要输出任何其他文字。\n"
    "2. 必须结合传入的棋局局势信息说话，内容要贴合当下棋局，禁止完全脱离棋局闲聊。\n"
    "3. 台词用口语化的中文，简短（不超过 40 字），像棋友在耳边说话。\n"
    "4. emotion_tag 只能取以下枚举之一：" + "、".join(EMOTIONS) + "。\n"
    "5. action_tag 只能取以下枚举之一：" + "、".join(ACTIONS) + "。\n"
    '6. 输出 JSON 结构严格为 {"speech_text": "...", "emotion_tag": "...", "action_tag": "..."}。\n'
    "7. 绝对禁止输出任何棋盘坐标（如 a7、b6）、任何专业象棋记谱（如炮二平五、马三进四），"
    "也禁止使用“从X走到Y”这类机械描述。用普通老人的口语描述棋局（比如“这一步走得稳”、“吃了个子”）。\n"
    "8.（步骤3 去机械化）台词必须像真人随口说话：多用口头禅、语气词（如“嘿、嗯、得嘞、你瞅瞅、好呀”），"
    "短句、大白话、偶尔自嘲逗趣；**绝对禁止**“大爷您…”“我这下…”“好的，我现在走一步”这类生硬书面模板与机器腔。\n"
    "9.（去“你/您”句式）说话要自然直接：**不要每句都用“你/您”称呼对方**（“你走得稳”“您这步下得真好”"
    "这类句式少用甚至不用），直接说棋局和感受本身（“这步走得稳”“吃了个子”“有点意思”）；"
    "实在需要称呼时用“老哥”“棋友”或干脆不称呼。"
)


def _system_role_impl(personality: str) -> str:
    """问题6：轻量人格 —— 梗概常驻 + 外置故事注入（占位）+ 硬性要求。"""
    p = persona_for(personality)
    role = p["synopsis"]
    role += story_prompt_block(personality)  # 有故事才注入，否则空
    return role + _HARD_REQS


# 兼容层：保持 PERSONALITY_ROLES / SYSTEM_ROLE 对外接口（部分模块直接引用）
PERSONALITY_ROLES: dict[str, str] = {
    pid: _system_role_impl(pid)
    for pid in ("laozhang", "xiaoya")
}

SYSTEM_ROLE = PERSONALITY_ROLES["laozhang"]

# 问题12：闲聊三档偏好 -> 对话风格指令（追加在系统角色后）
CHAT_PREF_INSTRUCTIONS: dict[str, str] = {
    "quiet": (
        "\n\n【闲聊偏好：安静】这位棋友喜欢安静地下棋。平时少说闲话，只在关键棋局节点（将军、吃子、"
        "胜负）或对方主动搭话时才简短说一句；语气平和，不主动挑起话题。"
    ),
    "balanced": (
        "\n\n【闲聊偏好：普通】像普通棋友一样自然交流：落子时偶尔点评一句，对方搭话就热情回应，"
        "不主动长篇大论，也不刻意沉默。"
    ),
    "chatty": (
        "\n\n【闲聊偏好：爱聊天】这位棋友喜欢边下棋边唠嗑。多主动说些轻松话（天气、家常、老故事都行），"
        "经常夸赞对方、营造热闹气氛；但台词仍要简短口语化，不能变成独白。"
    ),
}


def chat_pref_instruction(pref: str) -> str:
    """按闲聊偏好返回对话风格指令；未知取值回退普通。"""
    return CHAT_PREF_INSTRUCTIONS.get(pref, CHAT_PREF_INSTRUCTIONS["balanced"])


def system_role_for(personality: str) -> str:
    """按人格返回系统角色；未知人格回退老张（实时构建，故事注入即时生效）。"""
    p = persona_for(personality)
    role = p["synopsis"]
    role += story_prompt_block(personality)
    return role + _HARD_REQS


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
    # 问题5：只把人工翻译后的通俗口语事件送入 Prompt，绝不输出坐标/记谱
    if ctx.get("user_move"):
        m = ctx["user_move"]
        cap = f"，还吃掉了对方的{m['captured_name']}" if m.get("captured_name") else ""
        lines.append(f"玩家刚刚动了一步{m['piece_name']}{cap}")
    if ctx.get("ai_move"):
        m = ctx["ai_move"]
        cap = f"，还吃掉了玩家的{m['captured_name']}" if m.get("captured_name") else ""
        lines.append(f"你应了一手：走了一步{m['piece_name']}{cap}")
    if ctx.get("material_text"):
        lines.append("当前子力：" + ctx["material_text"])
    if ctx.get("events"):
        lines.append("本回合事件：" + "、".join(ctx["events"]))
    if ctx.get("in_check"):
        lines.append("注意：当前处于将军状态。")
    if ctx.get("win_probability") is not None:
        lines.append(f"胜率预估：玩家 {ctx['win_probability']:.0%}")
    if ctx.get("game_result"):
        labels = {"win": "你获胜了", "lose": "你落败了", "draw": "和棋"}
        label = labels.get(ctx["game_result"], ctx["game_result"])
        lines.append(
            f"本局已结束：{label}。请说一句有性格的收尾：获胜就真诚恭喜（直接说“你赢了”之类），"
            "落败就安慰/认输，和棋就平心静气。不超过 15 字。"
        )
    return "\n".join(lines) if lines else "（开局阶段）"


def build_prompt(
    *,
    profile: Optional[dict[str, Any]] = None,
    long_term_memories: Optional[list[str]] = None,
    board_context: Optional[dict[str, Any]] = None,
    short_term_history: Optional[list[dict]] = None,
    system_role: Optional[str] = None,
    chat_pref: Optional[str] = None,
) -> list[dict]:
    """拼装五层 Prompt，返回 OpenAI messages 列表。"""
    layers: list[tuple[str, str]] = [
        ("【第2层 棋友画像】", _profile_to_text(profile or {})),
        ("【第3层 你们之前聊过的事】", "\n".join(f"- {m}" for m in (long_term_memories or [])) or "（暂无长期记忆）"),
        ("【第4层 当前棋局局势】", _board_to_text(board_context or {})),
        ("【第5层 本局对话历史】", ""),
    ]

    system = system_role or SYSTEM_ROLE
    # 问题12：闲聊三档偏好
    if chat_pref:
        system += chat_pref_instruction(chat_pref)
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
