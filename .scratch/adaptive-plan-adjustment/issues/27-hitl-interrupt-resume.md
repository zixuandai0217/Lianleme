---
status: delivered
delivered_in: 4c3fdb9
feature: adaptive-plan-adjustment
ticket: 27
blocked_by: ["26"]
---

# 27 — HITL interrupt / resume + 超时兜底

**What to build:** 命中风险条件（伤病风险高、连续多次大幅调整、目标冲突）时，系统不自动改计划，而是把这次调整挂成「等你决定」：给出风险描述、推荐方案和另外两个选项，用户选完才落地。用户 5 分钟没回来，系统自动采用最保守的推荐方案并标明是代为选择，计划永远不卡在待确认；重复提交不重复改动，过期后的选择有明确答复。

**Blocked by:** 26 可查询调整作业 + pending / detail

**Status:** ready-for-agent

- [ ] AC1：命中条件（伤病健康评分 ≤3，或连续 3 次调整幅度 >20%，或目标冲突）时作业进入 `pending_choice`，载荷含风险原因码、风险描述、支撑证据、恰好 3 个选项（首个 `recommended=true`）与到期时间；此时计划未被修改（前后比对一致）。
- [ ] AC2：未命中条件时作业直接 `applied`，不产生 interrupt 载荷、不出现在待确认列表。
- [ ] AC3：提交选项后作业落为 `applied`，计划按所选方案变更（如 `reduce_intensity` 的幅度落在声明区间），结果记录 `chosen_by=user` 与所选项，详情可回看。
- [ ] AC4：resume 幂等：同一作业重复提交同一选项返回同一终态且计划只被改动一次；提交不同选项返回 4xx 冲突语义且不覆盖已落地结果。
- [ ] AC5：超时兜底：5 分钟内未选择时作业自动以推荐（保守）方案落地，状态 `expired_no_choice`、`chosen_by=timeout_default`；此后再 resume 返回「已按保守方案应用」的终态且不二次改动；他人作业 resume 403。
