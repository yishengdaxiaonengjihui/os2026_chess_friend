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
| 🀄 楚河汉界 | 棋盘中央河界文字，text-anchor+dominant-baseline 双居中；河界带内删去中间列纵向线（仅留左右边框），视觉更清爽 |
| 👥 多用户登录 | 登录页创建账号或选择已有账号，各账号棋谱/画像/记忆完全隔离，随时切换/退出 |
| 🗂️ 三 Tab 主界面 | 登录后进入主界面：「开始对局」「棋谱管理」「通用设置」，而非直接开局 |
| ⚙️ 对局设置 | 玩家执红先/黑后（执黑时 AI 先行）、AI 棋友（老张/小雅）、AI 棋力（低/中/高/自动自适应） |
| 📖 棋谱管理 | 每局标注 胜/负/和/未结束 四状态，可加精（⭐）、删除；查看时**整页变成对局室样式的回放界面**（无弹窗）：大棋盘 + 开局/上一手/下一手/终局 + 高亮最近一手 + 返回棋谱列表 |
| 🏠 主界面整洁 | 「开始对局」页只有对局设置+开始按钮，对局室不参与该页；点「开始对局」后整页变成对局室，点「返回主菜单」回到设置 |
| 🔧 通用设置 | 账号管理（改名/删除/退出）、主题（预留）、背景音乐（预留）、模型管理（运行时切换 LLM，失败自动回退） |
| ✨ 移动轨迹 | 落子后从源格到目标格画出淡出的轨迹线+终点圆点（用户橙/AI 蓝），方便看清走向 |
| 📖 棋谱库 | 对局自动落库，随时回看逐手棋谱与事件（含胜负） |
| 🎭 人格切换 | 老张/小雅人格随时切换，后端同步 LLM 人设并重置聊天记忆 |
| ♟️ 送吃保护 | 走棋后老帅受攻的着法被过滤并友好提示；结局只余将死/被将死/和棋 |
| 🏆 绝杀判赢 | 引擎中局候选着过滤"送将"伪着法 + `is_checkmate` 字段修复 + 响应新增 `result`/`game_over` 字段，将死/困毙精确判胜（前端优先用 result 渲染，无需吃掉老将）；**结局必开口**——终局绕过随机言语触发强制说收尾（Prompt 注入"本局已结束：你获胜了/落败/和棋"指令，LLM 空输出时回退老张/小雅人格固定收尾台词，保证"你赢了"必说） |
| 🗣️ 言语触发决策 | 落子不一定说话：强事件（将军/吃子/胜负）约 60% 发言、弱事件约 8%、8s 冷却与「连续 10 步必说一句」保底，把开口频率压到真人水平，避免 AI 话痨或冷场 |
| 🎲 走法多样性 | 开局库加权随机选着 + 中局在候选着中按胜率加权随机（非总走深搜最优），让棋友风格更像真人；**开局棋谱坐标已修正**（黑方顺手炮/屏风马/跳边马三条坐标错误：顺炮原先永远不合法、屏风马误写成往边角跳），棋谱只管**前 5 手**（`OPENING_BOOK_MAX_MOVE=5`，5 个半回合），之后纯引擎；**动态胜率控制**——auto 档局内按 EMA 平滑的用户胜率每 2 手调节一次难度（死区 ±5%、范围 [1,6]，赢则升档变强、输则降档变弱），引擎中局候选再按 `targetUserWinProb`（默认 0.5）选"下一步用户胜率最接近 50%"的着（被压制 ≤35% 时走最优不故意放水），把对局维持在势均力敌 |
| 🧹 输入过滤 | 语音/文字噪音（过短、纯标点表情、语气词）直接忽略；连续消息只响应最新一条，避免误触发刷屏 |
| 💬 闲聊三档 | 通用设置可选 安静/普通/爱聊天，Prompt 注入对应对话风格，控制 AI 唠嗑频率 |
| 🪶 轻量人格 | 人格设定外置 personas.json：梗概常驻 + 背景往事（story 注入「你记得的往事」）+ 短回忆片段（stories 供主动叙事随机讲），改 JSON 即可换人设，无需改代码 |
| 📖 主动叙事框架 | 参考 ProactiveAgent「节拍器」：开场打招呼、长时间静默时按手数间隔限频主动说话——静默时**讲人格章节式故事线**（老张《无字棋子》/小雅《棋盘住进脑子》，各 4 段：源头→发展→高潮→收尾，保留《棋王》《后翼弃兵》改编事实），**先抛源头、一点一点往后讲**：会话内按顺序推进下一段、本回合事件（吃子/将军/马/车）命中时从该故事**源头**重新讲起、讲完换新故事；**跨局续讲**（进度存画像 `story_state`，下次开局接着讲）；情绪/动作随内容多样化（回忆偏沉思、得意配微笑）；回退家常语气词库，不打断 LLM 点评，真正交给数字人播报 |
| 🔑 双凭证 | 小雅使用独立的魔珐星云 AppId/AppSecret（按人格分叉），切换人格时前端用对应凭证重建数字人会话 |
| 📴 降级开关 | `ENABLE_DIGITAL_HUMAN=false` 时完整保留象棋、对话、记忆逻辑，仅不渲染 3D 数字人 |
| 🖥️ 对局室锁单屏 | 对局室固定全屏无页面滚动条：棋盘随视口高度缩放（保持 9:10 比例），右栏信息列仅内部滚动，任何窗口不溢出 |
| ⏳ AI 真人感停顿 | 用户落子后 AI 先"琢磨"：0.8~1.8s 随机思考延迟（关键局面再延长），期间播思考动画与嘟囔台词，再落子 |
| 🗨️ 台词去机械化 | 内置口语库（老张/小雅各一组）：思考嘟囔、落子口头禅、吃子/将军/优劣势短句、用户长考 30s 主动搭话（整局≤2 次，简短语气词）；Prompt 硬性禁止"大爷您/我这下/机器腔"，并**去"你/您"句式**（直接说"这步走得稳"而非"你走得稳"，固定台词库同步清理）；人设梗概注入口癖；AI 落子前不再每手必嘟囔 |
| 🎤 语音输入闭环 | 对局室麦克风大按钮：Web Speech 中文识别 → 转写显示 → 后端 `/api/chat` 入记忆生成回复 → 数字人高优先级插播（barge-in）；噪音自动过滤、不支持时优雅降级；**尾音回声兜底**——数字人发声即静默麦克风、播完等 1.8s 再恢复，前端 3s 时间窗内做"台词相似度/子串"回声判定，后端 `/api/chat` 再对"最近一句 AI 台词的后缀/子串"判噪音丢弃（双保险，杜绝"数字人刚说完最后几个字被录进用户发言"） |
| 🏮 温暖棋馆风 | 全站暖色美化：木纹暖调 + 朱红点缀 + 暖金主按钮；Tab 大图标卡片式；聊天气泡带小尾巴；棋盘木纹立体边框；保持适老化大字号高对比 |

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
│   │   │   ├── speech_trigger_decider.py # 言语触发决策（落子是否说话）
│   │   │   ├── input_filter.py           # 输入过滤（噪音/连续消息去抖）
│   │   │   ├── persona_store.py          # 轻量人格仓库（personas.json）
│   │   │   ├── narrative_driver.py       # 主动叙事节拍器（讲人格短回忆 + 手数限频）
│   │   │   ├── avatar_dispatcher.py        # 具身指令分发器(状态机/表演队列/打断)
│   │   │   ├── xmov_client.py              # 星云协议适配层(情绪/动作映射+SSML)+时序调度
│   │   │   └── ws_hub.py                   # 对局 WebSocket 事件中心(数字人状态/棋局事件)
│   │   ├── models/               # Pydantic 数据模型
│   │   └── db/                   # SQLite 访问层
│   ├── vendor/xiangqi/           # vendored logic.js 引擎（MIT，含 NOTICE 归属）
│   └── tests/                    # pytest 单测
├── scripts/                      # 演示/运维脚本：demo_engine.py + cdp_e2e_check.js（CDP 前端 E2E）+ self_check.py（一键自检）+ package.py（赛事打包）
├── docs/                         # 交付文档（DELIVERY.md / DELIVERY.html / DELIVERY.pdf）
├── dist/                         # 打包产物（scripts/package.py 生成，不入库）
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

启动后直接访问 <http://127.0.0.1:8000/> 即为棋盘页面（API 与页面同源同端口）；交互式 API 文档在 <http://127.0.0.1:8000/docs>。Docker 部署后访问 <http://127.0.0.1:8010/>（见方式二）。

### 方式二：Docker Compose

```bash
cp .env.example .env              # 先复制配置（compose 依赖 .env 存在）
docker compose up -d --build
```

> 镜像内已装 Node.js（引擎运行时）并拷贝 backend/frontend/vendor 三件套，`./data` 挂载持久化画像/棋谱；**宿主端口 8010**（容器内 8000，与本地开发端口一致，避开常见 8000 占用）；国内构建加速：`.env` 配 `PIP_INDEX_URL`（compose build 自动透传）。
> 无魔珐星云账号时：设置 `ENABLE_DIGITAL_HUMAN=false`，数字人模块自动降级，其余业务完整可用。
> 魔珐星云邀请码：`XJKA436Y6J`（注册可获 1000 免费开发积分）。

### 方式三：交付包（赛事提交）

```bash
python scripts/package.py         # 产出 dist/os2026_chess_friend_v<版本>.zip + SHA256SUMS + manifest
```

> 交付包自动排除 `.git/.env/data/临时目录`；交付文档见 [docs/DELIVERY.md](docs/DELIVERY.md)（同内容 PDF：`docs/DELIVERY.pdf`，HTML 源可再打印）。

## 环境变量配置

见 [.env.example](.env.example)：

| 变量 | 说明 |
| --- | --- |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 大模型（OpenAI 兼容协议）。默认火山方舟 `doubao-seed-2.0-mini`（`LLM_THINKING_OFF=1` 关闭思考模式），可换 GLM/Qwen 等 |
| `XMOV_APP_ID` / `XMOV_APP_SECRET` | 魔珐星云 SDK 鉴权（真机联调启用）—— 老张 |
| `XMOV_XIAOYA_APP_ID` / `XMOV_XIAOYA_APP_SECRET` | 小雅的独立星云凭证（双凭证按人格分叉；留空则回退老张凭证） |
| `XMOV_LAOZHANG_*` / `XMOV_XIAOYA_*` | 星云形象/音色资产 ID |
| `ENABLE_DIGITAL_HUMAN` | 数字人模块总开关，默认 `true` |
| `SPEECH_TRIGGER_ENABLED` | 言语触发决策总开关，默认 `true`（关闭后落子每次都发言） |
| `ENGINE_DIVERSITY` / `ENGINE_DIVERSITY_PROB` / `ENGINE_DIVERSITY_OPENING` | 引擎走法多样性：总开关 / 中局加权随机概率（默认 0.45）/ 开局加权随机是否启用 |

## 开源贡献边界

> 本仓库**不复制第三方源码**，依赖通过 pip / submodule 引入；README 明确标注 License。

### ✅ 本项目自研核心模块（重点开源贡献）

- `chess_context_parser`：棋局状态解析，引擎原始输出 → 结构化博弈上下文
- `chess_engine`：象棋引擎适配层（FEN <-> 棋盘转换、AI 应手、评估/胜率、将军/将死判定）
- `memory_manager`：分层记忆适配器（短期 / Mem0 长期 / SQLite 结构化画像）
- `prompt_builder`：五层 Prompt 组装器（人格梗概 + 闲聊偏好注入）
- `speech_trigger_decider`：言语触发决策（强/弱事件发言概率、冷却、连续静默保底）
- `input_filter`：输入过滤（噪音判定 + 连续消息只响应最新）
- `persona_store` / `personas.json`：轻量人格仓库（梗概常驻 + 背景往事 + 短回忆片段）
- `narrative_driver`：主动叙事节拍器（讲人格短回忆 / 家常话 + 手数限频）
- `avatar_dispatcher`：具身指令分发器（表演队列、状态机、语音打断）
- `xmov_client`：魔珐星云协议适配层（情绪/动作映射、SSML 组装）+ 表演时序调度
- `ws_hub`：对局 WebSocket 事件中心（数字人状态 / 棋局事件实时推送）
- `avatar-adapter.js`：前端数字人适配层（星云 SDK 优先，Web Speech 朗读降级；队列调度 + 情绪超时重置 + 按人格双凭证重建）
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

**人格故事改编来源**（两位棋友的背景往事与短回忆片段为**二次改编创作**，非原作文本，特此注明）：
- 老张（张生）故事改编自：阿城《棋王》
- 小雅（陆雅）故事改编自：沃尔特·特维斯《后翼弃兵》（The Queen's Gambit）

## 开发路线图

- [x] **第一阶段（基础打通，引擎已接入）**：棋局解析模块、LLM 链路、基础台词输出 ✅；象棋引擎 AI 应手/评估/胜负判定 ✅；**前端棋盘 + FastAPI 联调 ✅（自研 vanilla JS 前端，同源服务）**
- [x] **第二阶段（记忆画像）**：分层记忆 ✅（短期会话 + 长期记忆适配器，未装 mem0 时自动降级 SQLite 子串召回）；**SQLite 画像读写与 diff 更新 ✅**（对局统计实时累加、开局/棋风/棋力识别、对局终结胜负落盘、长期记忆摘要）
- [x] **第三阶段（数字人链路）**：具身指令分发器状态机 ✅（IDLE/THINKING/SPEAKING + 表演队列 + 语音打断）；星云协议适配层 ✅（情绪→SDK emotion 枚举、动作→KA 关键动作、SSML 组装）；对局 WS 事件中心 ✅（后端推 thinking/speaking/idle + 棋局事件）；前端数字人适配层 ✅（星云 XmovAvatar litesdk 优先，Web Speech 中文朗读/文字降级）；**待真机**：加载 litesdk 后在浏览器渲染 3D 数字人（需在可联网环境）
- [ ] **第四阶段（打磨交付）**：交互打磨已完成 ✅（悔棋、棋谱库、人格切换、送吃保护与三结局兜底、AI 思考改为"让我想想…"）；**交互大改造已完成 ✅**（言语触发决策、数字人队列调度与情绪超时、引擎走法多样性、输入过滤、闲聊三档偏好、轻量人格、主动叙事框架、双凭证小雅）；**真人感收尾已完成 ✅**（绝杀判赢修复 + 全链路单测、说话频率下调、主动叙事台词真正播报 + 两位棋友人格故事落地、去"你/您"句式，含 `scripts/cdp_e2e_check.js` CDP 前端 E2E 验证——脚本同时校验后端响应含 result/game_over，可抓"旧后端未重启"回归）；**第四轮打磨已完成 ✅**（①开局棋谱坐标修正——顺手炮不再永远缺席、屏风马不再往边角跳，棋谱限前 5 手；②录音尾音双保险——前端恢复延时 1.8s + 3s 回声窗，后端台词后缀/子串判噪；③结局必开口——将死/困毙终局数字人强制说"你赢了"类收尾，LLM 空输出回退人格固定台词；④故事口语化改写 + 事件匹配 + 情绪多样化 + 会话内去重）；**第五轮打磨已完成 ✅**（①动态胜率控制——auto 档局内按胜率 EMA 动态调难度 + 引擎目标胜率选着，把用户胜率稳定在 ~50% 势均力敌；②章节式连续叙事——故事线 4 段"先抛源头、一点一点往后讲"、事件命中从源头重讲、跨局续讲存画像）；**第六轮打磨已完成 ✅**（①故事台词不再重复两遍——事件命中且正在讲该线时继续当前进度不重讲（连续性优先），另加"最近已讲窗口"（保留最近 6 条）防同一句紧挨着重讲，讲完整条线才换新故事；②状态栏"老张在思考"硬编码修复——落子瞬间状态栏显示当前人格名（选小雅即"小雅想想怎么走"），CDP E2E 新增人格名回归检查；③新增 `scripts/self_check.py` 一键自检——personas 结构/章节叙事推进/引擎含目标胜率/开局应着合法性/后端健康/前端关键元素/数据库回环，9 项一键跑）；**赛事收尾已完成 ✅**（①Docker 可复现——Dockerfile 修复容器缺 Node/前端/引擎三件套 + compose 加速透传与数据卷，**已在 WSL Ubuntu 实跑 `docker compose up -d --build` 验证通过**（构建/页面/引擎/数据卷/env 注入全绿，端口 8010）；②交付文档——`docs/DELIVERY.md` + `DELIVERY.html` + `DELIVERY.pdf`（Edge 打印）；③提交打包——`scripts/package.py` 产出 `dist/` 压缩包 + SHA256SUMS + manifest）；剩余（主观/真人项）：Prompt 调优、演示录屏
- [ ] **第五阶段**：10-11 前打包提交赛事（oscc@oschina.cn）

## 免责声明

本项目生成的用户画像**仅基于下棋行为的偏好统计**，用于娱乐陪伴参考，**不属于任何医疗或心理诊断**，不采集用户真实身份信息。所有记忆与画像数据本地存储（SQLite / Chroma），不向第三方上传。

## 许可证

[MIT](LICENSE)（自研代码）；复用组件按其各自协议（见上表）。
