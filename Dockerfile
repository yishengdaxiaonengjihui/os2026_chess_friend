# OS2026 适老化数字人中国象棋棋友 —— 可复现构建
# 用 python:3.12-slim 单阶段：装 Node（引擎）→ 装 Python 依赖 → 拷贝应用
# 构建加速（可选）：docker compose 从 .env 透传 PIP_INDEX_URL
FROM python:3.12-slim

WORKDIR /app

# 国内构建加速（可选）：compose build 时透传，未配置则用官方源
ARG PIP_INDEX_URL=

# Node.js：象棋引擎通过 node 执行 vendor/xiangqi/logic.js（engine_host.js 宿主）
RUN apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"}

# 应用本体：后端（FastAPI）+ 前端（同源 serve）+ vendored 引擎（离线可复现）
COPY backend ./backend
COPY frontend ./frontend
COPY vendor ./vendor

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
