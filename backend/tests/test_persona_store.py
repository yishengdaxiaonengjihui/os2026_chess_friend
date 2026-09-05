"""问题6：轻量人格 —— 梗概常驻 + 外置故事 JSON 占位。"""
import json
from pathlib import Path

from backend.app.core import persona_store as ps
from backend.app.core.prompt_builder import system_role_for


def test_personas_loaded():
    personas = ps.list_personas()
    assert "laozhang" in personas and "xiaoya" in personas


def test_synopsis_always_present():
    """梗概常驻：系统角色始终包含人格梗概。"""
    assert "老张" in system_role_for("laozhang")
    assert "小雅" in system_role_for("xiaoya")


def test_story_placeholder_empty_by_default():
    """外置故事默认占位为空：不注入「你记得的往事」段落。"""
    assert ps.story("laozhang") == ""
    assert "你记得的往事" not in system_role_for("laozhang")


def test_story_injected_when_present(monkeypatch):
    """外置故事非空时注入系统角色（占位机制按需启用）。"""
    monkeypatch.setattr(ps, "story", lambda p: "你年轻时在厂里下棋赢过车间主任。")
    sys_role = system_role_for("laozhang")
    assert "你记得的往事" in sys_role
    assert "车间主任" in sys_role


def test_personas_json_is_editable():
    """人格数据外置为 JSON，可直接编辑。"""
    f = Path(__file__).resolve().parents[2] / "backend" / "app" / "core" / "personas.json"
    assert f.exists()
    data = json.loads(f.read_text(encoding="utf-8"))
    assert "laozhang" in data["personas"]
    assert "synopsis" in data["personas"]["laozhang"]
    assert "story" in data["personas"]["laozhang"]


def test_persona_synopsis_has_speech_style():
    """步骤3：人格梗概含说话风格（口癖/禁书面模板），注入系统角色。"""
    lao = system_role_for("laozhang")
    xia = system_role_for("xiaoya")
    # 口癖描述
    assert "口头禅" in lao or "说话风格" in lao
    assert "说话风格" in xia
    # 禁书面模板
    assert "大爷您" in lao and "大爷您" in xia
    # 硬性要求第 8 条去机械化
    assert "去机械化" in lao
    assert "机器腔" in xia
