# 练了么 — AI 健身教练

全栈 AI 健身应用：体型分析、个性化训练计划、AI 陪练对话、体重追踪。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 19 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| 后端 | FastAPI + SQLAlchemy (async) + LangChain + LangGraph |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| LLM | 阿里云百炼 DashScope（DeepSeek-V3 / Qwen-VL） |
| 基础设施 | Docker Compose（Postgres + Redis + MinIO） |

## 快速开始（本地开发）

> 前置要求：Python ≥ 3.11、Node.js ≥ 18、[uv](https://docs.astral.sh/uv/)

### 1. 克隆项目

```bash
git clone <repo-url> && cd Lianleme
```

### 2. 启动后端

```bash
cd backend
cp .env.example .env   # 系统 Key 仅供明确的内部任务使用，不会回退给登录用户
uv sync                # 安装全部 Python 依赖（自动创建 .venv）
uv run uvicorn app.main:app --reload --port 8000
```

首次启动会自动创建 SQLite 数据库（`dev.db`）和所有表。

可选的音素级口型由 Rhubarb Lip Sync v1.14.0 提供；缺失时语音仍可播放，前端自动使用能量口型。安装脚本会校验官方发布包 SHA-256，二进制保存在忽略目录 `backend/.tools/rhubarb/`：

```bash
cd backend
./scripts/install_rhubarb.sh
```

Apple Silicon 需要先安装 Rosetta，因为 Rhubarb 官方 macOS 包仅提供 x86_64 版本。Linux 与 Docker 使用官方 Linux x86_64 包。安装到自定义目录时，将脚本输出的路径写入 `RHUBARB_BIN`。

### 3. 启动前端

```bash
cd web
npm install
npm run dev
```

浏览器打开 http://localhost:5173 即可。前端通过 Vite proxy 自动代理 `/api` 到后端 `localhost:8000`。

注册或首次登录后，用户需要自行前往通义千问或 OpenAI 官方平台申请 API Key，再到“我的 → AI 服务密钥”中配置。本平台不生成、不发放也不共享供应商 Key。Key 经 AES-256-GCM 加密保存，对外只返回掩码；未配置时数字教练、体型分析和训练计划生成均不可用。数字教练语音目前需要通义千问 Key，并使用用户账号可访问的公共音色。

### 4.（可选）Docker Compose 全套环境

如果需要 PostgreSQL + Redis + MinIO 完整环境：

```bash
cd infra/docker
cp ../../backend/.env.example .env   # 编辑 .env，DATABASE_URL 改为 PostgreSQL
docker compose up -d
```

## 项目结构

```
Lianleme/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/          # 路由（user/vision/plan/coach/weight/admin）
│   │   ├── core/         # 配置、数据库、存储
│   │   ├── models/       # SQLAlchemy ORM 模型
│   │   ├── schemas/      # Pydantic 请求/响应模型
│   │   └── services/     # 业务逻辑（AI/用户/体重/训练计划）
│   ├── .env.example      # 环境变量模板
│   └── pyproject.toml    # Python 依赖
├── web/                  # React 前端
│   ├── src/
│   │   ├── api/          # API 客户端 + 类型定义
│   │   ├── components/   # UI 组件（shadcn/ui）
│   │   ├── hooks/        # 自定义 Hooks
│   │   └── pages/        # 页面（dashboard/analysis/plan/coach/weight/admin）
│   └── package.json      # Node 依赖
└── infra/docker/         # Docker Compose + Dockerfile
```

## 核心功能

- **体型分析**：上传全身照 → Qwen-VL 视觉模型分析 → 体型分类 / 体脂估算 / 肌群评分 / 历史记录
- **训练计划**：根据体型分析自动生成 7 天个性化训练计划
- **AI 陪练**：流式对话教练，训练上下文感知，对话历史持久化
- **体重追踪**：每日打卡 + 趋势图表
- **管理后台**：用户统计 + 用户列表
