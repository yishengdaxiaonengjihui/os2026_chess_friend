"""长期记忆 + 画像持久化（SQLite 降级路径）测试。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.memory_manager import LongTermMemory, ProfileStore


def test_long_term_add_search(tmp_path):
    db = str(tmp_path / "mem_test.db")
    mem = LongTermMemory("u-mem-1", db_path=db)
    mem.add("用户喜欢用炮进攻", {"type": "pref"})
    mem.add("用户开局偏爱仙人指路", {"type": "opening"})
    hits = mem.search("炮 进攻")
    assert any("炮" in h for h in hits)
    # 降级路径下：无关查询也按关键词召回，至少返回部分记忆
    assert len(mem.search("炮")) >= 1


def test_profile_merge_diff(tmp_path):
    db = str(tmp_path / "profile_test.db")
    store = ProfileStore(db_path=db)
    cur = store.get("u-p-1")
    assert cur["style"] == "未知（待对局观察）"
    merged = store.merge_diff("u-p-1", {"style": "稳健型", "strength": "中级", "": "ignored"})
    assert merged["style"] == "稳健型"
    assert merged["strength"] == "中级"
    again = store.get("u-p-1")
    assert again["style"] == "稳健型"  # 持久化
    # 空值不覆盖
    store.merge_diff("u-p-1", {"style": ""})
    assert store.get("u-p-1")["style"] == "稳健型"


def test_profile_stats_accumulate(tmp_path):
    """跨对局统计累加：第二局在既有统计上继续。"""
    db = str(tmp_path / "acc_test.db")
    store = ProfileStore(db_path=db)
    import backend.app.core.game_stats as gs

    stats = gs.fresh_stats()
    for _ in range(6):
        gs.update_live_stats(stats, {"from": "a6", "to": "a5", "piece": "P"}, None, 0.5)
    gs.finalize_game(stats, "win")
    store.merge_diff("u-acc", {"stats": stats})
    stored = store.get("u-acc")["stats"]
    assert stored["games"] == 1 and stored["wins"] == 1

    # 第二局从画像读出统计继续累加
    stats2 = store.get("u-acc").get("stats") or gs.fresh_stats()
    for _ in range(6):
        gs.update_live_stats(stats2, {"from": "a6", "to": "a5", "piece": "P"}, None, 0.4)
    gs.finalize_game(stats2, "lose")
    store.merge_diff("u-acc", {"stats": stats2})
    stored2 = store.get("u-acc")["stats"]
    assert stored2["games"] == 2 and stored2["wins"] == 1 and stored2["losses"] == 1
