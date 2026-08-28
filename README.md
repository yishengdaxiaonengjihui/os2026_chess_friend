# 适老化数字人中国象棋棋友

> 2026 上海开源软件应用创新大赛（OS2026）· 开源 AI 工具赛道 · 魔珐星云企业命题
> 让 AI「活」起来：基于魔珐星云具身交互智能的创新应用

面向**居家独居老年群体**的 AI 数字人象棋棋友：真实中国象棋博弈 + 长期记忆 + 结构化用户画像 + 具身数字人表情/语音/动作反馈，打造一位「记得你棋风和喜好」的老朋友式棋友。

- 不是无脑哄人的玩具 Bot：复用成熟开源象棋引擎（α-β 剪枝），具备真实博弈能力
- 不是两张皮：棋局事件 → LLM 台词 → 数字人情绪/动作，全链路驱动
- 跨对局记忆：Mem0 长期记忆 + SQLite 结构化画像，AI 记得住你
- 适老化降级：老旧设备可关闭 3D 数字人，保留完整棋局/对话/记忆逻辑

---

## 目录

- [核心特性](#核心特性)
- [技术架构](#技术架构)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [环境变量配置](#环境变量配置)
- [开源贡献边界](#开源贡献边界)
- [开发路线图](#开发路线图)
- [免责声明](#免责声明)
- [许可证](#许可证)

---

## 核心特性

| 能力 | 说明 |
| --- | --- |
| 🎮 真实象棋博弈 | 复用 [ryoi/xiangqi](https://github.com/ryoi/xiangqi) logic.js 引擎（α-β 剪枝、置换表、开局库、胜率评估），自研 FEN 对接适配层 |
| 🧠 分层记忆 | 本局短期会话记忆 + Mem0 非结构化长期记忆 + SQLite 结构化用户画像，三者分工协作 |
| 🎭 人格化陪伴 | 棋局事件（将军/吃子/胜负）驱动 LLM 生成人格台词、情绪、动作 |
| 🗣️ 具身数字人 | 魔珐星云 XmovAvatar SDK：TTS、口型同步、情绪表情、关键动作、语音打断（barge-in） |
| 📊 用户画像 | 基于下棋行为统计棋风/棋力/开局/战绩，SQLite 持久化 + diff 更新，跨对局累加（娱乐参考，非医疗诊断） |
| ↩️ 悔棋 | 一键悔棋：回退用户与 AI 上一轮（棋盘/统计/棋谱/对局状态同步回滚） |
| 🤝 和棋/🏳 认输 | 和棋：AI 按当前局面胜率自动判断是否同意；认输：本局判负；均写入棋谱与长期记忆 |
| 🀄 楚河汉界 | 棋盘中央河界文字，text-anchor+dominant-baseline 双居中，像素级精准 |
| ✨ 移动轨迹 | 落子后从源格到目标格画出淡出的轨迹线+终点圆点（用户橙/AI 蓝），方便看清走向 |
| 📖 棋谱库 | 对局自动落库，随时回看逐手棋谱与事件（含胜负） |
| 🎭 人格切换 | 老张/小雅人格随时切换，后端同步 LLM 人设并重置聊天记忆 |
| ♟️ 送吃保护 | 走棋后老帅受攻的着法被过滤并友好提示；结局只余将死/被将死/和棋 |
| 📴 降级开关 | `ENABLE_DIGITAL_HUMAN=false` 时完整保留象棋、对话、记忆逻辑，仅不渲染 3D 数字人 |

## 技术架构

```
┌─────────────────────────────────────────────┐
│ 前端层（复用 ryoi/xiangqi）                    │
│  棋盘 UI / 落子交互 / FEN 输出 / 象棋引擎      │
│  魔珐星云 WebGL XmovAvatar SDK（数字人渲染）    │
│  全局开关 ENABLE_DIGITAL_HUMAN                 │
└──────────────WebSocket───────────────────────┘
┌─────────────────────────────────────────────┐
│ 后端 FastAPI ｜ 会话调度层                      │
│  session/user/game 管理、参数校验、限流        │
└────────────────业务调用──────────────────────┘
┌─────────────────────────────────────────────┐
│【核心自研编排层 ★ 本项目主要开源贡献】          │
│  chess_context_parser  棋局状态解析模块        │
│  memory_manager        分层记忆管理器          │
│  prompt_builder        五层 Prompt 组装器      │
│  llm_client            强约束 LLM 客户端       │
│  avatar_dispatcher     具身指令分发器(状态机)  │
└────────────────数据读写──────────────────────┘
┌─────────────────────────────────────────────┐
│ 存储层                                       │
│  SQLite：会话快照/对局元数据/结构化画像/棋谱    │
│  ChromaDB：向量库（由 Mem0 内部接管）           │
└─────────────────────────────────────────────┘
外部：大模型 API（OpenAI 兼容）· 魔珐星云 XmovAvatar 云端 SDK
```

### 关键链路（用户落子）

1. 前端棋盘点击（自研 vanilla JS，零依赖离线可跑）→ 高亮合法着法 `GET /api/moves/legal`
2. 前端提交 `{game_id, from_sq, to_sq}` → `POST /api/moves`，后端用引擎校验合法性（非法着法 400）
3. 后端执行象棋引擎 → AI 落子、评估分数、胜率、棋局事件；`user_fen`/`new_fen` 由后端统一计算
4. `chess_context_parser` 将原始引擎输出转为结构化博弈上下文 JSON
5. `memory_manager`：本局记忆写入 + Mem0 召回 top-4 长期记忆 + 读取 SQLite 画像
6. `prompt_builder` 拼装五层 Prompt → `llm_client` 强约束输出 `{speech_text, emotion_tag, action_tag}`
7. `avatar_dispatcher`：AI 落子回传棋盘 + 异步驱动数字人表演队列，支持语音打断

### Prompt 五层结构

1. 系统角色设定（约束 JSON 输出、情绪/动作枚举）
2. SQLite 结构化用户画像
3. Mem0 召回的长期记忆摘要
4. 结构化棋局局势信息（禁止直接传原始 FEN）
5. 本局短期会话对话历史

## 目录结构

```
os2026_chess_friend/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── main.py               # 应用入口 / 路由 / WebSocket
│   │   ├── config.py             # 环境变量配置（LLM / 魔珐星云 / 开关）
│   │   ├── api/                  # REST + WS 接口层
│   │   ├── core/                 # ★ 自研核心模块
│   │   │   ├── chess_context_parser.py   # 棋局状态解析
│   │   │   ├── chess_engine.py           # 象棋引擎适配层(node+logic.js)
│   │   │   ├── game_stats.py             # 对局统计/棋风棋力/画像生成
│   │   │   ├── js/engine_host.js         # Node 引擎宿主脚本
│   │   │   ├── memory_manager.py
│   │   │   ├── prompt_builder.py
│   │   │   ├── llm_client.py
│   │   │   ├── avatar_dispatcher.py        # 具身指令分发器(状态机/表演队列/打断)
│   │   │   ├── xmov_client.py              # 星云协议适配层(情绪/动作映射+SSML)+时序调度
│   │   │   └── ws_hub.py                   # 对局 WebSocket 事件中心(数字人状态/棋局事件)
│   │   ├── models/               # Pydantic 数据模型
│   │   └── db/                   # SQLite 访问层
│   ├── vendor/xiangqi/           # vendored logic.js 引擎（MIT，含 NOTICE 归属）
│   └── tests/                    # pytest 单测
├── scripts/                      # 演示/运维脚本（demo_engine.py）
├── frontend/                     # 自研 vanilla JS 前端（棋盘/棋友面板，联调完成）
├── docker-compose.yml            # 一键部署
├── Dockerfile
├── requirements.txt
├── .env.example                  # 环境变量模板
└── README.md
```

## 快速开始

### 方式一：本地开发

```bash
cd os2026_chess_friend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # 按需填入 LLM / 魔珐星云密钥
uvicorn backend.app.main:app --reload
```

启动后直接访问 <http://127.0.0.1:8000/> 即为棋盘页面（API 与页面同源同端口）；交互式 API 文档在 <http://127.0.0.1:8000/docs>。

### 方式二：Docker Compose

```bash
docker compose up -d
```

> 无魔珐星云账号时：设置 `ENABLE_DIGITAL_HUMAN=false`，数字人模块自动降级，其余业务完整可用。
> 魔珐星云邀请码：`XJKA436Y6J`（注册可获 1000 免费开发积分）。

## 环境变量配置

见 [.env.example](.env.example)：

| 变量 | 说明 |
| --- | --- |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 大模型（OpenAI 兼容协议）。默认火山方舟 `doubao-seed-2.0-mini`（`LLM_THINKING_OFF=1` 关闭思考模式），可换 GLM/Qwen 等 |
| `XMOV_APP_ID` / `XMOV_APP_SECRET` | 魔珐星云 SDK 鉴权（真机联调启用） |
| `XMOV_LAOZHANG_*` / `XMOV_XIAOYA_*` | 星云形象/音色资产 ID |
| `ENABLE_DIGITAL_HUMAN` | 数字人模块总开关，默认 `true` |

## 开源贡献边界

> 本仓库**不复制第三方源码**，依赖通过 pip / submodule 引入；README 明确标注 License。

### ✅ 本项目自研核心模块（重点开源贡献）

- `chess_context_parser`：棋局状态解析，引擎原始输出 → 结构化博弈上下文
- `chess_engine`：象棋引擎适配层（FEN <-> 棋盘转换、AI 应手、评估/胜率、将军/将死判定）
- `memory_manager`：分层记忆适配器（短期 / Mem0 长期 / SQLite 结构化画像）
- `prompt_builder`：五层 Prompt 组装器
- `avatar_dispatcher`：具身指令分发器（表演队列、状态机、语音打断）
- `xmov_client`：魔珐星云协议适配层（情绪/动作映射、SSML 组装）+ 表演时序调度
- `ws_hub`：对局 WebSocket 事件中心（数字人状态 / 棋局事件实时推送）
- `avatar-adapter.js`：前端数字人适配层（星云 SDK 优先，Web Speech 朗读降级）
- Docker-Compose 部署、降级开关、适老化业务逻辑

### 🔁 复用依赖（MIT / Apache-2.0 兼容）

| 仓库 | 复用内容 | 协议 |
| --- | --- | --- |
| [ryoi/xiangqi](https://github.com/ryoi/xiangqi) | 前端棋盘；`logic.js` 象棋引擎（α-β剪枝/置换表/开局库，vended 于 `backend/vendor/xiangqi`，含 NOTICE 归属） | MIT |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | 长期记忆 SDK（仅嵌入，不起独立服务） | Apache-2.0 |
| [chroma-core/chroma](https://github.com/chroma-core/chroma) | 嵌入式向量数据库（Mem0 底层存储） | Apache-2.0 |
| FastAPI 官方 | Web 框架 | MIT |

> vendored `logic.js` 原样内置（未修改引擎逻辑），仅通过自研 `engine_host.js` + `chess_engine.py` 粘合层以 FEN 对接，保证 Docker 构建可离线复现。

### 📖 参考借鉴（仅设计思路，未复制源码）

- [sealdad/chess_with_llm](https://github.com/sealdad/chess_with_llm)：棋局事件 → 人格台词映射
- [psychopathdev/voxavatar](https://github.com/psychopathdev/voxavatar)：数字人表演队列/状态机/barge-in
- [open-talking/OpenTalking](https://github.com/open-talking/OpenTalking)：编排架构、分层记忆思想
- [IceyVanci/llm-xiangqi](https://github.com/IceyVanci/llm-xiangqi)：中国象棋 Web+LLM 交互设计

## 开发路线图

- [x] **第一阶段（基础打通，引擎已接入）**：棋局解析模块、LLM 链路、基础台词输出 ✅；象棋引擎 AI 应手/评估/胜负判定 ✅；**前端棋盘 + FastAPI 联调 ✅（自研 vanilla JS 前端，同源服务）**
- [x] **第二阶段（记忆画像）**：分层记忆 ✅（短期会话 + 长期记忆适配器，未装 mem0 时自动降级 SQLite 子串召回）；**SQLite 画像读写与 diff 更新 ✅**（对局统计实时累加、开局/棋风/棋力识别、对局终结胜负落盘、长期记忆摘要）
- [x] **第三阶段（数字人链路）**：具身指令分发器状态机 ✅（IDLE/THINKING/SPEAKING + 表演队列 + 语音打断）；星云协议适配层 ✅（情绪→SDK emotion 枚举、动作→KA 关键动作、SSML 组装）；对局 WS 事件中心 ✅（后端推 thinking/speaking/idle + 棋局事件）；前端数字人适配层 ✅（星云 XmovAvatar litesdk 优先，Web Speech 中文朗读/文字降级）；**待真机**：加载 litesdk 后在浏览器渲染 3D 数字人（需在可联网环境）
- [ ] **第四阶段（打磨交付）**：交互打磨已完成 ✅（悔棋、棋谱库、人格切换、送吃保护与三结局兜底、AI 思考改为"让我想想…"）；剩余：Prompt 调优、Docker-Compose 可复现、演示录屏、PDF 文档
- [ ] **第五阶段**：10-11 前打包提交赛事（oscc@oschina.cn）

## 免责声明

本项目生成的用户画像**仅基于下棋行为的偏好统计**，用于娱乐陪伴参考，**不属于任何医疗或心理诊断**，不采集用户真实身份信息。所有记忆与画像数据本地存储（SQLite / Chroma），不向第三方上传。

## 许可证

[MIT](LICENSE)（自研代码）；复用组件按其各自协议（见上表）。
