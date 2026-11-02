# 练了么 — 规格索引（PRD / ADR → issue specs）

本目录把 `docs/plans/` 的两份 PRD 与 `docs/adr/` 中此前**尚未实现**的架构决策，切成 14 份可独立交付的规格。每份规格是一个独立 issue，交付后 `frontmatter.status` 从 `ready-for-agent` 改为 `delivered` 并回填 `delivered_in` 提交号；当前 14 份规格与 45 张工单均已交付。

已经落地、因此**没有**出 spec 的条目：PRD P0-1 鉴权与权限收口、P0-2 正式登录接入（已由 JWT + 用户/管理员分离 + `test_auth_guards.py` 覆盖）；ADR-0006 西海岸口语风格教练（CoachGraph 与计划/反馈文案已落地）。

## 规格清单

| # | 目录 | 一句话 | 来源 |
|---|---|---|---|
| 1 | [`analysis-task-persistence/`](analysis-task-persistence/issue.md) | 体型分析任务从进程内字典升为持久实体：状态机、租约执行器、任务/历史分层、稳定错误码 | P0-3 |
| 2 | [`media-asset-storage/`](media-asset-storage/issue.md) | 原图进对象存储、DB 只存 key、私有 bucket + 短时签名 URL、校验与清理 | P0-4 |
| 3 | [`coach-stream-protocol/`](coach-stream-protocol/issue.md) | 陪练流从裸文本 token 收口为结构化 SSE 事件流，服务端清洗 + 服务端快捷动作 | P0-5 |
| 4 | [`quality-gate-and-ci/`](quality-gate-and-ci/issue.md) | 单一入口质量门（typecheck/lint/单测/smoke）+ CI 三阶段 + 失败阻断 | P0-6 |
| 5 | [`observability-baseline/`](observability-baseline/issue.md) | 请求关联 ID、单行结构化日志、异常记录、`/health/ready` 依赖探测 | P0-7 |
| 6 | [`first-run-onboarding/`](first-run-onboarding/issue.md) | 首页/计划页/分析页三处分叉的「下一步」收敛为一套纯函数判定 | P1-1 |
| 7 | [`plan-explainability/`](plan-explainability/issue.md) | 计划响应新增解释（生成依据 + 最近一次调整说明），旧计划三档降级 | P1-2 |
| 8 | [`workout-session-loop/`](workout-session-loop/issue.md) | 静态清单升级为可恢复训练会话；打卡改投递调整作业并回四段式反馈 | P1-3 + P1-4 |
| 9 | [`weight-trend-insights/`](weight-trend-insights/issue.md) | 体重从图表变解读：7/30 天窗口、阶段极值、训练频率对照、目标偏离 | P1-5 |
| 10 | [`reminder-recall/`](reminder-recall/issue.md) | 进程内 tick 提醒引擎 + 站内收件箱 + 六条规则（含 3/7/14 天召回阶梯） | P1-6 |
| 11 | [`admin-ops-console/`](admin-ops-console/issue.md) | 后台从单页展示升级为三页只读工作台：搜索/筛选/详情/CSV 导出 | P1-7 |
| 12 | [`adaptive-plan-adjustment/`](adaptive-plan-adjustment/issue.md) | 5 路并行分析器 + Merge Node + HITL 风险中断（替代单维度完成率路由） | ADR-0001/0003/0004 |
| 13 | [`pose-correction/`](pose-correction/issue.md) | PoseGraph：MediaPipe 关键点 → 动作周期切分 → 规则+模型质量评估 → 纠错反馈 | ADR-0002 |
| 14 | [`muscle-heatmap-3d/`](muscle-heatmap-3d/issue.md) | Three.js 3D 肌肉热力图，把 VisionGraph 的部位评分渲染成发光材质 | ADR-0005 |

## 跨 spec 约定（读任何一份之前先看这三条）

1. **迁移与数据模型**：全组只在 [`analysis-task-persistence`](analysis-task-persistence/issue.md) 的「迁移与数据模型落地约定」一节定义——ORM 是唯一事实源、迁移与模型手写对齐、按交付追加 revision、可回滚、方言判断只出现在兼容层。凡引入新表/新列（1、2、7、8、10、12、13）都必须遵守它，不得各自另立约定。
2. **异步机制只有两条，且分工写死**：一次性作业（分析、调整、重缩略图、Web Push 发送）走 [`analysis-task-persistence`](analysis-task-persistence/issue.md) 定义的 DB 驱动执行器；周期性触发（提醒）走 [`reminder-recall`](reminder-recall/issue.md) 的轻量 tick，tick 内不开协程跑重活。打卡后调整的作业语义归 [`adaptive-plan-adjustment`](adaptive-plan-adjustment/issue.md)，[`workout-session-loop`](workout-session-loop/issue.md) 只投递并读取状态。
3. **观测字段只在 [`observability-baseline`](observability-baseline/issue.md) 定义**，其他 spec 只引用不重复；错误码、脱敏与日志字段以其为准。

## 测试 seam 约定

- 后端最高 seam 一律是 **FastAPI 路由层**（httpx ASGITransport + `dependency_overrides`，Graph/LLM/存储客户端换替身），prior art：`backend/tests/test_auth_guards.py`、`test_coach_stream.py`、`test_user_api_keys.py`。
- 前端最高 seam 是**纯 TS 判定函数**（prior art：`web/src/pages/analysis/flow.ts` + `flow.test.ts`），页面只做 vitest + jsdom 接线断言（prior art：`coach-page.integration.test.ts`、`api-key-gate.test.tsx`）。
- 例外与新 seam 在各 spec 的「Testing Decisions」里单独论证：姿态上行流（[`pose-correction`](pose-correction/issue.md) 新增三个 HTTP 端点，仍复用同一 ASGI 骨架）、3D 渲染（[`muscle-heatmap-3d`](muscle-heatmap-3d/issue.md) 把「评分 → 视觉参数」抽成纯函数，渲染只冒烟）、质量门（[`quality-gate-and-ci`](quality-gate-and-ci/issue.md) 验证的是门本身会红）。

## 建议实施顺序

```
第一批（系统性风险，彼此可并行）
  1 analysis-task-persistence  ──┐  迁移约定与执行器是全组地基
  3 coach-stream-protocol        │
  4 quality-gate-and-ci          │
  5 observability-baseline     ──┘
        │
第二批（依赖第一批的契约）
  2 media-asset-storage      ← 任务执行器 + 迁移约定
  7 plan-explainability      ← 迁移约定；调整结论字段
  8 workout-session-loop     ← 调整作业（12 的状态语义）+ 执行器
  10 reminder-recall         ← 执行器（重通道）+ 迁移约定
  6 first-run-onboarding     ← 8/7 的入口与空态
  9 weight-trend-insights    ← 档案 schema 同步
  11 admin-ops-console       ← 行为轨迹依赖 8/10 的落库
第三批（AI 深度，可在第一批之后独立推进）
  12 adaptive-plan-adjustment ← 执行器 + 观测字段；被 8 消费
  13 pose-correction          ← 12 的可选输入；被 8 的会话页挂载
  14 muscle-heatmap-3d        ← VisionGraph 既有评分，无强依赖
```

## 规格来源

- `docs/plans/2026-06-02-launch-backlog.md`（P0/P1 任务清单与验收口径）
- `docs/plans/2026-06-02-production-readiness-roadmap.md`（短板与未完成能力）
- `docs/adr/0001`–`0005`（已决策未实现的架构能力）
- `CONTEXT.md`（领域词汇：VisionGraph / AdjustGraph / CoachGraph / PoseGraph / WorkoutGraph、BYOK、完成率、疲劳度评分、伤病风险、Human-in-the-loop、关键点、动作周期、Muscle Heatmap）

## 工单

规格已竖切成 45 张 tracer bullet 工单，依赖关系与可立即开工的 frontier 见 [TICKETS.md](TICKETS.md)。每份规格旁多了 `issues/` 子目录，文件名为全局依赖序号 `<NN>-<slug>.md`。

## 维护

- 校验脚本：`.scratch/_tools/verify_specs.py`（检查 frontmatter、8 个小节、user stories 数量、Implementation Decisions 里的路径泄漏、seam 与 prior art 是否写明）。新增或修改规格后跑一次。
- 路径约定：正文不写文件路径，路径只出现在每份规格末尾的「相关文件」一节。
