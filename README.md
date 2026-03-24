# 练了么（Lianleme）

练了么是一个 **AI 主导的健身搭子应用**，面向减脂新人，提供训练、饮食、体重管理和 AI 教练建议。

当前 V1 采用 **3 Tab 用户信息架构**：
- 练了么：训练主流程（内含 AI 搭子入口）
- 吃了么：饮食记录与摄入管理
- 瘦了么：体重趋势与周报（内含“我的”入口）

---

## 1. 项目目标

V1 的目标是用最小可交付架构快速上线，同时保证后续可演进：
- 单一对外网关，避免客户端直连多服务
- AI 编排独立服务，便于模型切换和链路升级
- 异步任务独立服务，支持拍照分析/周报等耗时场景
- 前后端目录语义清晰，降低团队沟通成本

---

## 2. 命名规范（已统一）

### 2.1 应用层（apps）
- `apps/mobile-client`：用户端（uni-app，多端）
- `apps/admin-console`：运营后台（Web）

### 2.2 服务层（services）
- `services/api-gateway`：对外 API 网关
- `services/profile-service`：用户资料与体重画像
- `services/ai-coach-service`：AI 教练编排（LangChain + LangGraph）
- `services/task-service`：异步任务（ARQ + Redis）

### 2.3 共享层（packages）
- `packages/contracts`：OpenAPI 与共享类型
- `packages/design-tokens`：设计令牌（颜色、字体、圆角等）

> 说明：命名统一采用“职责 + service/console/client”模式，避免 `domain/worker/orchestrator` 这类不直观词汇造成理解偏差。

---

## 3. 仓库结构

```text
Lianleme/
├─ apps/
│  ├─ mobile-client/         # 用户端（uni-app）
│  └─ admin-console/         # 后台（Vue + Vite）
├─ services/
│  ├─ api-gateway/           # 对外 API /v1/*
│  ├─ profile-service/       # 用户资料服务
│  ├─ ai-coach-service/      # AI 编排服务
│  └─ task-service/          # 异步任务服务
├─ packages/
│  ├─ contracts/             # OpenAPI / Python shared models
│  └─ design-tokens/         # 设计令牌
├─ infra/
│  └─ docker/                # Dockerfile / env 示例
├─ docs/
│  └─ architecture/          # 架构和运行文档
└─ tests/
   └─ e2e/                   # E2E 说明/脚本
```

---

## 4. 技术栈

### 4.1 用户端
- uni-app + Vue 3 + Pinia
- 目标平台：微信小程序 / H5 / App（同一套代码）

### 4.2 后台
- Vue 3 + Vite + TypeScript

### 4.3 后端服务
- FastAPI
- Redis + ARQ（异步任务）
- LangChain + LangGraph（AI 编排）

### 4.4 数据与部署
- PostgreSQL
- Docker Compose（V1 单区容器化部署）

---

## 5. AI 模型策略

- 文本模型：`deepseek-v3.2`
- 视觉模型：`qwen3-vl-flash`
- 语音模型：V1 暂不启用

安全边界：仅健康管理建议，不提供医疗诊断或处方。

---

## 6. 快速开始
<!-- 补充当前仓库实际可用的根目录安装命令与小程序启动命令；影响快速启动说明；通过核对 package.json 与 docker-compose.yml 验证。 -->

### 6.1 环境要求
- Node.js 20+
- Python 3.11+
- `uv`（Python 包管理/运行）
- Docker Desktop（可选，但推荐）

### 6.2 安装前端依赖

```bash
npm install
npm install --workspace apps/mobile-client --legacy-peer-deps
npm install --workspace apps/admin-console --legacy-peer-deps
```

### 6.3 本地启动后端（四个终端）

```bash
cd services/profile-service && uv run python -m app.main
cd services/ai-coach-service && uv run python -m app.main
cd services/task-service && uv run python -m app.main
cd services/api-gateway && uv run python -m app.main
```

### 6.4 启动前端

```bash
npm run dev:mobile:h5
npm run dev:mobile:mp
npm run dev:admin
```

### 6.5 Docker 一键启动

```bash
docker compose up --build
```

网关文档：`http://localhost:8000/docs`

---

## 7. API 总览（Gateway）

客户端统一调用网关 `api-gateway`：

### 7.1 首页聚合
- `GET /v1/home/workout`
- `GET /v1/home/diet`
- `GET /v1/home/progress`

### 7.2 用户与资料
- `POST /v1/auth/login`
- `POST /v1/auth/logout`
- `GET /v1/auth/me`
- `GET /v1/profile`
- `PUT /v1/profile`
- `GET /v1/profile/trend`

### 7.3 训练与饮食
- `GET /v1/workout/today`
- `POST /v1/workout/logs`
- `GET /v1/diet/today`
- `POST /v1/diet/logs`

### 7.4 AI 与计划
- `POST /v1/coach/message`
- `POST /v1/plan/generate`
- `POST /v1/plan/regenerate`

### 7.5 拍照与周报
- `POST /v1/photo/analyze`
- `GET /v1/photo/tasks/{task_id}`
- `GET /v1/report/weekly`

### 7.6 后台接口
- `GET /v1/admin/dashboard`
- `GET /v1/admin/users`
- `GET /v1/admin/recipes`
- `GET /v1/admin/workout-templates`
- `GET /v1/admin/ai-config`

---

## 8. 测试

```bash
cd services/api-gateway && uv run --with pytest pytest -q
cd services/profile-service && uv run --with pytest pytest -q
cd services/ai-coach-service && uv run --with pytest pytest -q
cd services/task-service && uv run --with pytest pytest -q
```

---

## 9. 常见问题

### Q1：为什么服务拆成四个而不是更多？
A：V1 面向 1-2 人团队，目标是最小可交付。四服务是当前性价比最高的分层：网关、资料域、AI 域、任务域。

### Q2：为什么 AI 单独服务？
A：模型和编排策略变化最快，独立后不会影响用户域和网关稳定性。

### Q3：为什么“我的”不单独做 Tab？
A：按产品决策，“我的”归入“瘦了么”，减少底部导航复杂度，突出训练/饮食/体重三主线。

---

## 10. 下一步建议

- 增加 OpenAPI 自动生成 SDK（mobile/admin 共用）
- 完善 task-service 的真实队列消费链路
- 增加网关鉴权与 RBAC（后台角色权限）
- 增加 E2E 自动化（小程序/H5/后台）
---

## 11. 目录作用速查（按协作视角）
<!-- Why: 补充“目录 -> 职责 -> 关键入口”的速查说明，降低新成员理解成本。 Scope: 仓库顶层目录及核心子目录说明。 Verify: 新同学仅阅读 README 本节即可知道每类改动应落在哪个目录。 -->

| 目录 | 主要作用 | 你通常会改什么 |
| --- | --- | --- |
| `.github/` | CI 配置（自动测试与构建） | `workflows/ci.yml` |
| `.claude/` | Agent 本地配置、hooks、skills 资源 | 一般不改业务逻辑 |
| `apps/mobile-client/` | 用户端（uni-app，多端） | `src/pages/*`、`src/api/client.js` |
| `apps/admin-console/` | 管理后台（Vue + Vite） | `src/App.vue`、`src/main.ts` |
| `services/api-gateway/` | 对外统一 API 网关，聚合内部服务 | `app/routes/*`、`app/clients.py` |
| `services/profile-service/` | 用户资料与体重画像服务 | `app/main.py` |
| `services/ai-coach-service/` | AI 教练编排服务（意图、安全、工具调用） | `app/agent/*`、`app/routes/internal.py` |
| `services/task-service/` | 异步任务服务（拍照分析、周报、队列） | `app/routes.py`、`app/worker.py`、`app/tasks/jobs.py` |
| `packages/contracts/` | 共享契约（OpenAPI + Python 类型） | `openapi/gateway.yaml`、`python/lianleme_contracts/*` |
| `packages/design-tokens/` | 共享设计令牌（颜色/字号/间距等） | `tokens.json` |
| `infra/docker/` | 运行环境与镜像模板 | `python-service.Dockerfile`、`.env.example` |
| `docs/architecture/` | 架构说明与运行手册 | `monorepo.md`、`runbook.md` |
| `tests/e2e/` | 端到端测试说明/脚本占位 | `README.md` |
| `docker-compose.yml` | 本地一键拉起基础设施与后端服务 | 服务端口、环境变量、依赖关系 |

### 快速定位建议
- 前端页面问题：先看 `apps/*/src/pages`。
- 接口聚合问题：先看 `services/api-gateway/app/routes`。
- AI 回复逻辑：先看 `services/ai-coach-service/app/agent/graph.py`。
- 异步任务状态问题：先看 `services/task-service/app/routes.py` 与 `app/worker.py`。
- 联调与部署问题：先看 `docker-compose.yml` 和 `docs/architecture/runbook.md`。
