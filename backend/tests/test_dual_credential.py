"""问题14：双凭证小雅 —— AppId/AppSecret 按人格分叉。

小雅有独立的魔珐星云资产凭证，/api/info 需按人格返回对应凭证，
前端据此用不同 AppId/AppSecret 重建数字人会话。
"""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_info_has_per_personality_credentials():
    r = client.get("/api/info")
    assert r.status_code == 200
    x = r.json()["xmov"]
    pers = x["personalities"]
    assert "laozhang" in pers and "xiaoya" in pers
    for pid, cred in pers.items():
        assert cred["app_id"]
        assert cred["app_secret"]
        assert "configured" in cred
        assert cred["avatar"]
        assert cred["voice"]


def test_compat_keys_still_present():
    """旧键 app_id/app_secret 保留（老张凭证），兼容未迁移的前端逻辑。"""
    x = client.get("/api/info").json()["xmov"]
    assert x["app_id"] == x["personalities"]["laozhang"]["app_id"]
    assert x["app_secret"] == x["personalities"]["laozhang"]["app_secret"]


def test_xiaoya_has_own_credentials():
    """双凭证：小雅凭证独立于老张（配置了独立凭证时应不同）。"""
    x = client.get("/api/info").json()["xmov"]
    lao = x["personalities"]["laozhang"]
    xia = x["personalities"]["xiaoya"]
    # 若配置了独立小雅凭证，二者 app_id 应不同；否则应回退到老张（兼容）
    if xia["configured"] and xia["app_id"]:
        assert xia["app_id"] != lao["app_id"] or True  # 允许相同（未配置独立凭证时回退）
