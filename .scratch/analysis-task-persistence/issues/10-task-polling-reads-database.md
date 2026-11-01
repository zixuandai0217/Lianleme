---
status: ready-for-agent
feature: analysis-task-persistence
ticket: 10
blocked_by: ["09"]
---

# 10 — 任务轮询改读数据库

**What to build:** 用户刷新页面、换台设备、或者赶上一次服务重启，再回来看，等待中的分析还在——状态从待执行推进到执行中，再到完成或失败，失败还给得出可读的原因分类。过期不再伪装成「任务不存在」：用户看到的是「已过期，可重新发起」，而不是一句让人以为数据被吞的 404。轮询接口从此只读数据库里的那一份事实，因此「谁在什么时候看到什么状态」不再取决于请求打到了哪个实例。状态取值固定为 `pending / processing / completed / failed / expired`，转移规则以分析任务持久化 spec 的状态机为准，本票不新增状态。

**Blocked by:** 09 分析任务实体与创建接口

**Status:** ready-for-agent

- [ ] 轮询接口只从数据库读取：重建应用实例（内存清空）后，凭任务标识仍能返回同一任务的状态与时间字段，不再返回 404。
- [ ] 响应字段完整且稳定：`status`（五态之一）、`stage`、`attempt`、`progress`、`result`、`error`（含 `code`、`message`、`retryable`）、`created_at`、`updated_at`、`expires_at`；`result` 与 `error` 互斥，未完成时两者皆空。
- [ ] 已过期任务返回 200 且 `status=expired`（不是 404）；从未存在的标识返回 404 且错误码为「任务不存在」；两者可被同一前端逻辑区分。
- [ ] 他人任务返回 403，响应体不含任何结果、错误详情或用户信息。
- [ ] 失败任务的 `error.code` 取自稳定错误码集合（`provider_auth_failed`、`provider_rate_limited`、`provider_timeout`、`output_unparsable`、`image_invalid`、`storage_unavailable`、`retry_exhausted`、`task_expired`、`internal_error`），`error.message` 为安全文案，不含供应商原始异常、堆栈或密钥。
- [ ] 轮询是只读且幂等的：同一任务连续多次轮询不改变其状态，也不重复触发执行或重复写入历史记录。
