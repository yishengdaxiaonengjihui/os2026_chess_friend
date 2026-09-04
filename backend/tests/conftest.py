"""pytest 全局配置：强制 mock 模式，测试不打真实 LLM、不读真实 .env 密钥。"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ["LLM_API_KEY"] = ""  # 覆盖 .env，强制 mock 模式
os.environ["SPEECH_TRIGGER_ENABLED"] = "0"  # 问题1：测试关闭言语触发，保证链路测试确定性
os.environ["ENGINE_DIVERSITY"] = "0"  # 问题8：测试关闭引擎多样性，保证引擎着法确定性
os.environ.setdefault("ENABLE_DIGITAL_HUMAN", "true")
os.environ.setdefault("SQLITE_PATH", "data/test_chess_friend.db")

ROOT = Path(__file__).resolve().parents[2]  # os2026_chess_friend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    """把 pytest 的临时目录根定向到工作区内，避免沙箱拦截系统临时目录的锁文件/清理。"""
    tmp_root = Path(os.environ.get("DSH_TESTS_TMP", str(ROOT / ".tmp_pytest_ws")))
    tmp_root.mkdir(parents=True, exist_ok=True)
    config._tmp_root_override = tmp_root


@pytest.fixture
def tmp_path(request):
    """覆盖内置 tmp_path：返回工作区内唯一子目录（绕过系统临时目录沙箱限制）。"""
    base = getattr(request.config, "_tmp_root_override", None) or (ROOT / ".tmp_pytest_ws")
    d = base / ("t-" + uuid.uuid4().hex[:12])
    d.mkdir(parents=True, exist_ok=True)
    yield d
