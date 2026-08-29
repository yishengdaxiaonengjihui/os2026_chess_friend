"""pytest 全局配置：强制 mock 模式，测试不打真实 LLM、不读真实 .env 密钥。"""
import os
import sys
from pathlib import Path

os.environ["LLM_API_KEY"] = ""  # 覆盖 .env，强制 mock 模式
os.environ["SPEECH_TRIGGER_ENABLED"] = "0"  # 问题1：测试关闭言语触发，保证链路测试确定性
os.environ.setdefault("ENABLE_DIGITAL_HUMAN", "true")
os.environ.setdefault("SQLITE_PATH", "data/test_chess_friend.db")

ROOT = Path(__file__).resolve().parents[2]  # os2026_chess_friend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
