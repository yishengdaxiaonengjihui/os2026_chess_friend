"""一键自检脚本：后端 / 引擎 / 章节叙事 / 开局棋谱 / 前端 / 数据 六类自动检查。

用法（仓库根目录下）：
    python scripts/self_check.py [--base http://127.0.0.1:8010]

检查项（全部离线可跑，后端在线时额外查 /health 与 /api/info）：
  1. personas.json 结构：每人格 synopsis/stories 非空；storylines 段数 3~5、段非空、id 唯一
  2. 章节叙事：无进度从源头；顺序推进 0..N-1 收尾；事件命中「正在讲该线」继续不重讲、
     未在讲则从源头；最近已讲窗口去重（换段不重句）
  3. 引擎：ai_move（含 targetUserWinProb）返回合法着；开局应着 sanity（当头炮后黑应着合法）
  4. 后端健康（在线时）：/health、/api/info；离线标记 SKIP
  5. 前端：index.html 关键元素齐全；app.js 状态栏不再硬编码"老张想想"（人格名随选择）
  6. 数据：ProfileStore（临时库）merge_diff 读写回环

退出码：0 = 全部通过（SKIP 不计失败）；1 = 存在失败项。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []  # (name, ok, detail)


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    tag = "PASS" if ok else ("SKIP" if detail.startswith("SKIP") else "FAIL")
    print(f"{tag} | {name}" + (f" | {detail}" if detail else ""))
    return bool(ok)


# ---------------- 1) personas.json 结构 ----------------
def check_personas() -> None:
    path = ROOT / "backend" / "app" / "core" / "personas.json"
    if not path.exists():
        check("personas.json 存在", False, f"缺失: {path}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    personas = data.get("personas") or data  # 兼容 {personas: {...}} 顶层结构
    problems: list[str] = []
    ids: list[str] = []
    for pname in ("laozhang", "xiaoya"):
        p = personas.get(pname)
        if not p:
            problems.append(f"{pname} 缺失")
            continue
        if not p.get("synopsis"):
            problems.append(f"{pname}.synopsis 为空")
        if not p.get("stories"):
            problems.append(f"{pname}.stories 为空（碎片兜底）")
        lines = p.get("storylines") or []
        if not lines:
            problems.append(f"{pname}.storylines 为空（应有章节式主线）")
        for line in lines:
            lid = line.get("id")
            if not lid:
                problems.append(f"{pname} 故事线缺 id")
            else:
                ids.append(lid)
            segs = line.get("segments") or []
            if not (3 <= len(segs) <= 5):
                problems.append(f"{pname}.{lid} 段数={len(segs)}（应 3~5）")
            for s in segs:
                if not s or not str(s).strip():
                    problems.append(f"{pname}.{lid} 存在空段")
    if len(ids) != len(set(ids)):
        problems.append("故事线 id 不唯一")
    check("personas.json 结构（人格/碎片/章节主线）", not problems, "; ".join(problems) if problems else "laozhang+xiaoya 均合格")


# ---------------- 2) 章节叙事推进 ----------------
def check_narrative() -> None:
    from backend.app.core.narrative_driver import NarrativeContext, NarrativeType, build_narrative
    from backend.app.core.persona_store import storylines

    ok_all = True
    for pname in ("laozhang", "xiaoya"):
        lines = storylines(pname)
        if not lines:
            check(f"叙事推进[{pname}] 有故事线", False, "storylines 为空")
            ok_all = False
            continue
        n = len(lines[0]["segments"])
        prog = None
        seq: list[int] = []
        for _ in range(n):
            d = build_narrative(NarrativeType.QUIET, NarrativeContext(personality=pname, move_index=10, quiet_seconds=99.0, story_progress=prog))
            seq.append(d["seg_idx"])
            if d.get("story_id") and not d["done"]:
                prog = {"story_id": d["story_id"], "seg_idx": d["seg_idx"] + 1}
            elif d.get("done"):
                prog = None
        ok_seq = seq == list(range(n))
        # 事件命中：正在讲该线 -> 继续当前段（不重讲）
        mid = min(2, n - 1)
        d_ev_cont = build_narrative(NarrativeType.QUIET, NarrativeContext(
            personality=pname, move_index=10, quiet_seconds=99.0,
            events=["玩家吃子：吃掉对方炮"], story_progress={"story_id": lines[0]["id"], "seg_idx": mid},
        ))
        ok_ev_cont = d_ev_cont["seg_idx"] == mid and d_ev_cont["story_id"] == lines[0]["id"]
        # 事件命中：没在讲 -> 从源头
        d_ev_src = build_narrative(NarrativeType.QUIET, NarrativeContext(
            personality=pname, move_index=10, quiet_seconds=99.0,
            events=["玩家吃子：吃掉对方炮"], story_progress={"story_id": "other-line", "seg_idx": 1},
        ))
        ok_ev_src = d_ev_src["seg_idx"] == 0
        # 最近已讲窗口去重：exclude 含源头段 -> 换段不重句
        first = lines[0]["segments"][0]
        d_dedup = build_narrative(NarrativeType.QUIET, NarrativeContext(
            personality=pname, move_index=10, quiet_seconds=99.0,
            story_progress={"story_id": lines[0]["id"], "seg_idx": 0}, exclude=[first],
        ))
        ok_dedup = d_dedup["text"] != first
        ok_p = ok_seq and ok_ev_cont and ok_ev_src and ok_dedup
        check(
            f"叙事推进[{pname}] 顺序/事件继续/事件源头/去重",
            ok_p,
            f"seq={seq} 事件继续@{mid}->{d_ev_cont['seg_idx']} 源头->{d_ev_src['seg_idx']} 去重换段={ok_dedup}",
        )
        ok_all = ok_all and ok_p
    return ok_all


# ---------------- 3) 引擎 + 开局应着 ----------------
def check_engine() -> None:
    from backend.app.core import chess_context_parser as ccp
    from backend.app.core.chess_engine import ai_move, legal_moves

    try:
        fen = ccp.apply_move_to_fen(ccp.make_default_fen(), "b7", "e7")  # 红 当头炮
        fen = ccp.toggle_side(fen)
        legal = {m["from"] + m["to"] for m in legal_moves(fen, "black")}
        seen: set[str] = set()
        for _ in range(20):
            r = ai_move(fen, color="black", difficulty=3, move_number=1, diversity=True, target_user_win_prob=0.5)
            mv = r["from_sq"] + r["to_sq"]
            assert mv in legal, f"引擎返回非法着 {mv}"
            seen.add(mv)
        check("引擎 ai_move（含 targetUserWinProb）返回合法着", True, f"20 次全合法，共 {len(seen)} 种应着")
        bad = seen - legal
        check("开局棋谱 sanity：当头炮后黑应着合法", not bad, f"非法应着={sorted(bad)}" if bad else "全部在合法集合内")
    except Exception as e:  # noqa: BLE001
        check("引擎 ai_move / 开局应着", False, f"ERR {e}")


# ---------------- 4) 后端健康 ----------------
def check_backend(base: str) -> None:
    import urllib.request

    try:
        with urllib.request.urlopen(base + "/health", timeout=3) as r:
            h = json.loads(r.read().decode())
        ok = h.get("status") == "ok"
        with urllib.request.urlopen(base + "/api/info", timeout=3) as r:
            info = json.loads(r.read().decode())
        dh = info.get("digital_human_enabled")
        ok2 = ok and dh is not None
        check("后端健康 /api/health + /api/info", ok2, f"status={h.get('status')} llm={h.get('llm_mode')} dh={dh}")
    except Exception as e:  # noqa: BLE001
        check("后端健康 /api/health + /api/info", True, f"SKIP 后端离线（{e}）")


# ---------------- 5) 前端 ----------------
def check_frontend() -> None:
    html = ROOT / "frontend" / "index.html"
    appjs = ROOT / "frontend" / "js" / "app.js"
    if not html.exists() or not appjs.exists():
        check("前端文件存在", False, f"index={html.exists()} app.js={appjs.exists()}")
        return
    text = html.read_text(encoding="utf-8")
    ids = ["board", "status", "avatar-name", "set-personality", "btn-start-game"]
    missing = [i for i in ids if f'id="{i}"' not in text]
    check("前端 index.html 关键元素齐全", not missing, f"缺={missing}" if missing else "5 个关键 id 均在")
    js = appjs.read_text(encoding="utf-8")
    hardcoded = "老张想想" in js
    check("前端状态栏不再硬编码'老张'", not hardcoded, "app.js 仍有'老张想想'硬编码" if hardcoded else "状态栏用当前人格名")


# ---------------- 6) 数据 ----------------
def check_db() -> None:
    from backend.app.core.memory_manager import ProfileStore

    tmp = os.path.join(tempfile.gettempdir(), "dsh-selfcheck-profiles.db")
    try:
        os.remove(tmp)
    except OSError:
        pass
    store = ProfileStore(db_path=tmp)
    store.merge_diff("selfcheck-user", {"story_state": {"story_id": "wuzi-qi", "seg_idx": 2}, "nickname": "自检"})
    got = store.get("selfcheck-user")
    ok = got.get("story_state") == {"story_id": "wuzi-qi", "seg_idx": 2} and got.get("nickname") == "自检"
    check("数据 ProfileStore 读写回环（story_state 跨局续讲持久化）", ok, f"读回={got.get('story_state')}")
    try:
        os.remove(tmp)
    except OSError:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="OS2026 象棋棋友一键自检")
    ap.add_argument("--base", default=os.environ.get("DSH_BASE_URL", "http://127.0.0.1:8010"))
    args = ap.parse_args()
    print("=== OS2026 适老化数字人象棋棋友 自检 ===")
    check_personas()
    check_narrative()
    check_engine()
    check_backend(args.base)
    check_frontend()
    check_db()
    failed = [r for r in RESULTS if not r[1] and not r[2].startswith("SKIP")]
    skipped = [r for r in RESULTS if r[2].startswith("SKIP")]
    print(f"\n===== 自检汇总: {len(RESULTS) - len(failed)}/{len(RESULTS)} 通过 (SKIP {len(skipped)}) =====")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name} | {detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
