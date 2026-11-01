# ADR-0001: 采用 5 路并行分析器架构增强训练计划调整

## 状态

已接受 (2026-10-27)

## 背景

当前 AdjustGraph 只基于**完成率**单一维度调整训练计划：
- 完成率 ≥ 80% → 增加 10-15% 训练量
- 完成率 < 50% → 降低 15-20% 训练量
- 其他情况 → 保持不变

这种简化逻辑存在问题：
1. **忽略用户状态**：高完成率可能来自咬牙坚持，用户实际已过度疲劳
2. **伤病风险**：连续高强度训练可能导致受伤，但系统无感知
3. **目标偏离**：体重/体脂未按预期变化时，单纯调整训练量无法解决问题
4. **技术深度不足**：作为简历项目，单一维度的调整逻辑无法体现 AI 应用的复杂性

项目优化目标是提升技术深度，使其适合作为 AI 应用工程师岗位的作品集。需要展示：
- LangGraph 的并行编排能力
- 多维度数据融合决策
- 真实健身场景的业务理解

## 决策

采用 **5 路并行分析器架构**，从以下维度综合评估用户状态：

```
analyze_input
    ↓
并行执行 5 个分析器：
  ├→ completion_analyzer    (完成率分析)
  ├→ fatigue_analyzer       (疲劳度分析)
  ├→ injury_risk_analyzer   (伤病风险分析)
  ├→ sleep_analyzer         (睡眠质量分析)
  └→ body_metrics_analyzer  (体重/体脂趋势分析)
    ↓
merge_results (汇总统一格式输出)
    ↓
decision_node (加权决策)
    ↓
apply_changes (生成调整后的计划)
```

### 统一输出格式

每个分析器返回：
```python
{
    "score": 0-10,        # 当前维度的健康评分
    "reason": str,        # 评分依据
    "suggestion": str     # 调整建议
}
```

### 数据来源

| 分析器 | 数据来源 |
|--------|----------|
| completion | 最近 7 天完成率数组 |
| fatigue | 用户打卡时主观上报（1-5 分） |
| injury_risk | 完成度推断 + 训练频率 + 疲劳度综合评估 |
| sleep | 用户每日输入睡眠时长和质量（1-5 分） |
| body_metrics | 体重记录表 + 体型分析历史表 |

### 实现模式

采用**混合模式**（详见 [ADR-0003](0003-hybrid-analyzer-implementation.md)）：
- completion/fatigue/sleep：纯规则计算 score，LLM 生成 reason/suggestion
- injury_risk/body_metrics：LLM 深度分析

## 后果

### 优势

1. **技术深度提升**
   - 展示 LangGraph 并行编排能力（5 路并行 → 汇总 → 决策）
   - 体现多维度数据融合的架构设计能力

2. **决策质量改善**
   - 避免过度训练：高完成率 + 高疲劳 + 睡眠不足 → 强制休息
   - 伤病预防：连续 6 天高强度 + 某动作完成率持续低 → 降低强度或替换动作
   - 目标追踪：体重停滞 + 计划执行良好 → 调整饮食建议或增加有氧

3. **用户体验**
   - 系统更"懂"用户状态，不再机械地只看完成率
   - 调整理由更透明（每个分析器都有 reason 字段）

### 权衡

1. **数据依赖增加**
   - 需要用户每日输入疲劳度和睡眠数据（打卡表单扩展 2 个字段）
   - 用户不填写时，对应分析器使用默认值（如 fatigue=3, sleep=3）

2. **LLM 成本上升**
   - injury_risk 和 body_metrics 分析器需要 LLM 深度分析
   - 每次调整触发 2 次额外 LLM 调用（但并行执行，延迟不增加）

3. **复杂度提升**
   - 5 个分析器需要单独测试
   - merge 节点的加权逻辑需要调优（初期采用简单平均，后续可引入领域知识）

4. **实现周期**
   - MVP 阶段每个分析器采用简化实现（2-3 天完成）
   - 后续可迭代优化规则和 LLM Prompt

## 备选方案

### 方案 A：线性增强型（6-8 节点串行）

```
analyze → risk_assessment → fatigue_check → 
条件路由 → adjust_intensity/adjust_volume/swap_exercises/insert_rest → 
validate
```

**未采用原因**：
- 串行执行延迟高（每个节点依赖前一个节点结果）
- 无法展示 LangGraph 的并行能力，技术亮点不足

### 方案 B：迭代优化型（循环结构）

```
analyze → generate_adjustment → simulate_outcome → 
(if not optimal) → refine_adjustment → simulate_outcome → ... 
(if optimal) → finalize
```

**未采用原因**：
- 实现复杂度高，MVP 阶段时间不足
- "simulate_outcome" 需要额外的预测模型，数据支撑不足
- 循环次数难以控制，可能导致 LLM 成本失控

### 方案 C：保持现状（单维度完成率）

**未采用原因**：
- 技术深度不足，无法支撑简历项目的差异化目标
- 与豆包视频等成熟产品相比无竞争力

## 相关决策

- [ADR-0003](0003-hybrid-analyzer-implementation.md) - 混合模式实现分析器
- [ADR-0004](0004-human-in-the-loop-risk-decisions.md) - 风险决策的人机协同机制
