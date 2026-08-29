"""问题5：四层术语净化 —— 坐标/记谱不进 Prompt、系统硬禁令、正则兜底过滤。"""
from backend.app.core.term_filter import sanitize_speech
from backend.app.core.prompt_builder import PERSONALITY_ROLES, _board_to_text


def test_sanitize_removes_coordinate_move():
    assert sanitize_speech("这一步从a6走到a5，稳当") == "这一步走了一步，稳当"
    assert sanitize_speech("马从a2进到b4，有点意思") == "马走了一步，有点意思"


def test_sanitize_removes_chinese_notation():
    assert sanitize_speech("炮二平五，这步还行") == "那一步，这步还行"
    assert sanitize_speech("你刚刚马三进四，我没想到") == "你刚刚那一步，我没想到"


def test_sanitize_removes_bare_coordinate():
    assert sanitize_speech("a7这步棋走得漂亮") == "这步棋走得漂亮"


def test_sanitize_keeps_plain_speech():
    s = "这一步走得挺稳当，咱们慢慢来。"
    assert sanitize_speech(s) == s


def test_board_to_text_contains_no_coordinates():
    ctx = {
        "user_move": {"from": "a6", "to": "a5", "piece": "P", "piece_name": "兵", "captured_name": ""},
        "ai_move": {"from": "b0", "to": "c2", "piece": "N", "piece_name": "马", "captured_name": "炮"},
        "events": ["将军：玩家被将军！"],
        "material_text": "红方: 兵5; 黑方: 卒5",
    }
    txt = _board_to_text(ctx)
    assert "a6" not in txt and "a5" not in txt and "b0" not in txt and "c2" not in txt
    assert "玩家刚刚动了一步兵" in txt
    assert "走了一步马" in txt


def test_system_role_has_hard_ban():
    role = PERSONALITY_ROLES["laozhang"]
    assert "坐标" in role and "炮二平五" in role and "从X走到Y" in role
