# 练了么 — 工单索引（45 张）

由 14 份规格竖切而来。每张票都是 tracer bullet：跨层、可单独 demo，声明了阻塞它的票。
工单文件位于 `.scratch/<feature>/issues/<NN>-<slug>.md`，`NN` 是全局依赖序号。

已交付 45/45 张（交付提交见各票 frontmatter 的 `delivered_in`）。

## 可立即开工（无阻塞且未交付）

（无：全部工单已交付）

## 全量表

### 批次 A — 地基

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 01 | [质量门入口（前后端质量命令 + 修跨平台用例）](quality-gate-and-ci/issues/01-quality-gate-entry.md) | `quality-gate-and-ci` | — | ✅ 已交付 |
| 02 | [CI 三阶段编排与失败阻断](quality-gate-and-ci/issues/02-ci-pipeline-and-merge-blocking.md) | `quality-gate-and-ci` | 01 | ✅ 已交付 |
| 03 | [结构化日志与请求关联 ID](observability-baseline/issues/03-structured-logs-and-request-id.md) | `observability-baseline` | — | ✅ 已交付 |
| 04 | [就绪探针与依赖健康检查](observability-baseline/issues/04-readiness-probe-and-dependency-health.md) | `observability-baseline` | 03 | ✅ 已交付 |
| 05 | [LLM 调用日志与脱敏](observability-baseline/issues/05-llm-call-logging-and-redaction.md) | `observability-baseline` | 03 | ✅ 已交付 |
| 06 | [迁移基线对齐与一致性测试](analysis-task-persistence/issues/06-migration-baseline-alignment.md) | `analysis-task-persistence` | 01 | ✅ 已交付 |

### 批次 B — 分析链路

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 07 | [今日接口区分「无计划 / 休息日」](workout-session-loop/issues/07-today-endpoint-no-plan-vs-rest-day.md) | `workout-session-loop` | — | ✅ 已交付 |
| 08 | [调整结论落盘最小契约](adaptive-plan-adjustment/issues/08-persist-adjustment-outcome.md) | `adaptive-plan-adjustment` | 06 | ✅ 已交付 |
| 09 | [分析任务实体与创建接口](analysis-task-persistence/issues/09-analysis-task-entity.md) | `analysis-task-persistence` | 06 | ✅ 已交付 |
| 10 | [任务轮询改读数据库](analysis-task-persistence/issues/10-task-polling-reads-database.md) | `analysis-task-persistence` | 09 | ✅ 已交付 |
| 11 | [DB 驱动执行器](analysis-task-persistence/issues/11-db-driven-executor.md) | `analysis-task-persistence` | 09 | ✅ 已交付 |
| 12 | [任务列表与历史对齐](analysis-task-persistence/issues/12-task-list-history-alignment.md) | `analysis-task-persistence` | 10 | ✅ 已交付 |
| 13 | [前端任务状态映射与终止态](analysis-task-persistence/issues/13-frontend-task-status-mapping.md) | `analysis-task-persistence` | 10 | ✅ 已交付 |
| 14 | [媒体资产实体 + 原图上传 + 签名读图](media-asset-storage/issues/14-media-asset-upload-signed-read.md) | `media-asset-storage` | 06、09 | ✅ 已交付 |
| 15 | [请求期校验 + 缩略图异步生成](media-asset-storage/issues/15-request-validation-thumbnail.md) | `media-asset-storage` | 11、14 | ✅ 已交付 |
| 16 | [资产清理与孤儿巡检](media-asset-storage/issues/16-asset-cleanup-orphan-sweep.md) | `media-asset-storage` | 15 | ✅ 已交付 |

### 批次 C — 陪练协议

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 17 | [陪练协议帧 + 服务端清洗 + 前端协议层](coach-stream-protocol/issues/17-coach-protocol-frames-and-cleanup.md) | `coach-stream-protocol` | — | ✅ 已交付 |
| 18 | [服务端快捷动作与教练状态](coach-stream-protocol/issues/18-server-quick-actions-and-coach-state.md) | `coach-stream-protocol` | 17 | ✅ 已交付 |
| 19 | [错误 / 中断 / 回放清洗](coach-stream-protocol/issues/19-error-interrupt-and-replay-cleanup.md) | `coach-stream-protocol` | 17 | ✅ 已交付 |

### 批次 D — 计划与训练

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 20 | [计划解释字段落库与读取](plan-explainability/issues/20-plan-explanation-persistence-and-read.md) | `plan-explainability` | 08 | ✅ 已交付 |
| 21 | [计划页解释卡 + 训练量摘要](plan-explainability/issues/21-plan-explanation-card-and-volume-summary.md) | `plan-explainability` | 20 | ✅ 已交付 |
| 22 | [训练会话实体 + 推进 / 恢复接口](workout-session-loop/issues/22-workout-session-entity-progress-resume.md) | `workout-session-loop` | 06、07 | ✅ 已交付 |
| 23 | [会话页（当前动作 / 进度 / 倒计时 / 跳过）](workout-session-loop/issues/23-session-page-exercise-progress-timer-skip.md) | `workout-session-loop` | 22 | ✅ 已交付 |

### 批次 E — 自适应调整

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 24 | [Analyzer 抽象 + 三路规则 + Merge Node](adaptive-plan-adjustment/issues/24-analyzer-abstraction-rule-merge.md) | `adaptive-plan-adjustment` | 06、08 | ✅ 已交付 |
| 25 | [两路 LLM 分析器 + 降级](adaptive-plan-adjustment/issues/25-llm-analyzers-with-degradation.md) | `adaptive-plan-adjustment` | 24、05 | ✅ 已交付 |
| 26 | [可查询调整作业 + pending / detail](adaptive-plan-adjustment/issues/26-queryable-adjustment-job.md) | `adaptive-plan-adjustment` | 11、24 | ✅ 已交付 |
| 27 | [HITL interrupt / resume + 超时兜底](adaptive-plan-adjustment/issues/27-hitl-interrupt-resume.md) | `adaptive-plan-adjustment` | 26 | ✅ 已交付 |
| 28 | [打卡投递作业 + 四段式反馈](workout-session-loop/issues/28-checkin-job-dispatch-four-part-feedback.md) | `workout-session-loop` | 11、20、22、26 | ✅ 已交付 |

### 批次 F — 产品闭环

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 29 | [下一步判定纯函数 + 首页引导卡](first-run-onboarding/issues/29-next-step-decision-and-home-guide.md) | `first-run-onboarding` | — | ✅ 已交付 |
| 30 | [计划页 / 分析页空态联动](first-run-onboarding/issues/30-plan-analysis-empty-state-sync.md) | `first-run-onboarding` | 29 | ✅ 已交付 |
| 31 | [体重趋势统计与解读区](weight-trend-insights/issues/31-weight-trend-stats-and-insights.md) | `weight-trend-insights` | — | ✅ 已交付 |
| 32 | [目标体重字段同步 + 偏离判定](weight-trend-insights/issues/32-target-weight-field-and-deviation.md) | `weight-trend-insights` | 31 | ✅ 已交付 |
| 33 | [提醒调度宿主 + 投递记录 + 收件箱](reminder-recall/issues/33-reminder-scheduler-inbox.md) | `reminder-recall` | 03、06 | ✅ 已交付 |
| 34 | [六条规则 + 幂等 / 上限 / 免打扰](reminder-recall/issues/34-six-rules-idempotency-cap-quiet-hours.md) | `reminder-recall` | 33 | ✅ 已交付 |
| 35 | [Web Push 重通道](reminder-recall/issues/35-web-push-heavy-channel.md) | `reminder-recall` | 11、33 | ✅ 已交付 |

### 批次 G — 管理后台

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 36 | [用户列表搜索 / 筛选 / flags](admin-ops-console/issues/36-user-list-search-filter-flags.md) | `admin-ops-console` | — | ✅ 已交付 |
| 37 | [用户详情聚合 + 脱敏](admin-ops-console/issues/37-user-detail-aggregation-masking.md) | `admin-ops-console` | 36 | ✅ 已交付 |
| 38 | [CSV 导出 + 导出审计](admin-ops-console/issues/38-csv-export-and-audit.md) | `admin-ops-console` | 36 | ✅ 已交付 |
| 39 | [三页工作台 + 权限回归](admin-ops-console/issues/39-three-page-console-permission-regression.md) | `admin-ops-console` | 36 | ✅ 已交付 |

### 批次 H — AI 深度

| # | 工单 | 规格 | 阻塞 | 状态 |
|---|---|---|---|---|
| 40 | [姿态会话 + 帧上行 + 周期切分](pose-correction/issues/40-pose-session-frame-cycles.md) | `pose-correction` | 06、07 | ✅ 已交付 |
| 41 | [规则评估 + 骨架高亮](pose-correction/issues/41-rule-evaluation-skeleton-highlight.md) | `pose-correction` | 40 | ✅ 已交付 |
| 42 | [模型增强 + 节流 + 降级](pose-correction/issues/42-llm-enhancement-throttle-fallback.md) | `pose-correction` | 41、05 | ✅ 已交付 |
| 43 | [隐私边界与聚合摘要](pose-correction/issues/43-pose-privacy-aggregates.md) | `pose-correction` | 40 | ✅ 已交付 |
| 44 | [评分→视觉映射 + 2D 降级](muscle-heatmap-3d/issues/44-score-to-visual-mapping.md) | `muscle-heatmap-3d` | — | ✅ 已交付 |
| 45 | [Three.js 3D 渲染 + 降级](muscle-heatmap-3d/issues/45-threejs-render-fallback.md) | `muscle-heatmap-3d` | 44 | ✅ 已交付 |

## 使用方式

1. 只领取「阻塞」全部完成、且状态仍为 `ready-for-agent` 的票（frontier）。
2. 一张票就是一次完整交付：`What to build` 是验收范围，`Acceptance criteria` 是完成定义。
3. 规格正文在同目录上一级的 `issue.md`；票与规格冲突时以票为准，并回头修规格。
4. 交付后把票与规格的 `status` 改为 `delivered` 并回填 `delivered_in`，再跑校验脚本。
5. 校验脚本：`.scratch/_tools/verify_tickets.py`；新增或调整票后跑一次。

## 已裁决的切票边界

- **08 的存储形态**：独立「调整结论」记录（一次调整一条、带稳定标识），计划侧只保存最近一次的引用，不复制理由文本；20 读引用、21 与 28 都投影同一来源，24 在该记录上扩展五维明细与合并分。
- **09 / 10 的切法**：09 以「测试可 verify」为完成定义（创建即持久、428 不产生记录、重启后仍可查），不为了页面可 demo 而引入内存读取过渡或双写；用户可感知的等待体验从 10 开始。
- **14 → 15 的缩略图空窗**：14 阶段历史接口的缩略图字段返回空值并带降级标记，前端走占位；缩略图在 15 补齐。这是刻意接受的中间态。
- **周期宿主只有一个**：16 的孤儿巡检挂在执行器（11）的定时清理上，不依赖 33；33 的 tick 只做规则判定与投递记录写入，不承担巡检，也不自建第二套定时器。
- **主链路 smoke 不单独成票**：本地质量门的完整档在 01，「CI 上无密钥确定性 + 换故障替身必红」在 02，避免为一张横切验证票再改一次全局编号。
- **统一脱敏环节归 05**：03 只定义日志形态与字段，脱敏由 05 的 LLM 调用日志负责，03 不再重复要求。
- **18 的「流式与非流式动作一致」**以路由层契约测试验证（同一输入两处输出一致），不要求该行为对用户直接可见。
- **29 内联 API 错误语义**：区分「资源不存在」与「请求失败」随 29 一起做，不单独成票——它是引导判定能正确的前提。
- **30 不依赖 07**：30 只消费周计划查询语义，07 改的是今日接口的三态，不构成 30 的阻塞边。
- **38 的两处二选一已钉死**：筛选 0 行返回仅表头的文件；被拒绝的导出同样写审计记录（含拒绝原因）。
- **33 的手动 tick 是内部/运维入口**，不是公开 HTTP 端点，因此不进入 39 的逐端点权限回归清单。
- **43 的摘要验收为契约级**：以「下游可只读获取且不含坐标」断言，不依赖 25 落地做端到端，故 43 不依赖 25。
