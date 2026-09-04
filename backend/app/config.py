"""全局配置：从 .env / 环境变量读取。

对齐 spec 2.4：LLM 接口、魔珐星云鉴权、ENABLE_DIGITAL_HUMAN 降级开关。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- LLM（OpenAI 兼容协议，默认火山方舟 Ark）----
    llm_api_key: str = ""
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/plan/v3"
    llm_model: str = "doubao-seed-2.0-mini"
    llm_thinking_off: bool = False
    llm_max_tokens: int = 320
    llm_temperature: float = 0.9

    # ---- 魔珐星云 XmovAvatar ----
    xmov_app_id: str = ""
    xmov_app_secret: str = ""
    xmov_ws_url: str = "https://nebula-agent.xingyun3d.com/user/v1/ttsa/session"
    xmov_laozhang_avatar: str = "AM032_V2_14200_new"
    xmov_laozhang_voice: str = "XMOV_HN_TTS__36"
    xmov_xiaoya_avatar: str = "AF045_8752_new"
    xmov_xiaoya_voice: str = "XMOV_HN_TTS__49"

    # ---- 降级开关：关闭数字人后保留其余全部业务 ----
    enable_digital_human: bool = True

    # ---- 言语触发决策（问题1）：默认开启“落子不一定说话”；测试环境关闭保确定性 ----
    speech_trigger_enabled: bool = True

    # ---- 象棋引擎（ryoi/xiangqi logic.js，vendor 内置）----
    engine_skill: int = 3          # 1(易)..6(难)
    engine_time_ms: int = 0        # 0=引擎默认时间预算
    engine_logic_path: str = ""    # 留空用 vendor 默认路径，可覆盖指定其他 logic.js

    # ---- 引擎走法多样性（问题8）：开局库加权随机 + 中局候选加权随机 ----
    engine_diversity: bool = True              # 总开关
    engine_diversity_prob: float = 0.45        # 中局走「加权候选」而非「深搜最优」的概率
    engine_diversity_opening: bool = True      # 开局阶段是否启用加权随机开局库

    # ---- 存储 ----
    sqlite_path: str = "data/chess_friend.db"
    chroma_dir: str = "data/chroma"

    # ---- 记忆参数 ----
    short_term_max_turns: int = 20
    long_term_recall_top_k: int = 4

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def xmov_configured(self) -> bool:
        return bool(self.xmov_app_id) and bool(self.xmov_app_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
