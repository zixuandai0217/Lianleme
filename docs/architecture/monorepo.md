# Why: 固化命名规范和职责边界，避免“同义词目录”导致理解成本上升。
# Scope: 服务命名、端应用命名、路径语义和责任划分。
# Verify: 新人仅看目录名就能判断服务职责和调用方向。

## 命名规范（V1）

- `apps/mobile-client`: 用户端（uni-app，多端统一代码）
- `apps/admin-console`: 运营中台（Web）
- `services/api-gateway`: 对外统一 API 网关
- `services/profile-service`: 用户资料与体重画像域
- `services/ai-coach-service`: AI 编排（LangChain + LangGraph）
- `services/task-service`: 异步任务与任务状态

## 端口与责任

- `:8000` `api-gateway`: 客户端唯一入口，聚合 `/v1/*`
- `:8010` `profile-service`: 用户资料读写
- `:8020` `ai-coach-service`: 对话/计划生成
- `:8030` `task-service`: 拍照任务、周报异步能力

## 用户端 IA（3 Tab）

- Tab1 `练了么`：训练主流程 + AI 搭子入口
- Tab2 `吃了么`：饮食记录与摄入管理
- Tab3 `瘦了么`：体重趋势 + 我的入口