# ADR-0003: 使用混合模式实现分析器（规则+LLM）

## 状态

已接受 (2026-10-27)

## 背景

[ADR-0001](0001-five-way-parallel-analyzers.md) 决定采用 5 路并行分析器架构。每个分析器需要输出统一格式：
```python
{
    "score": 0-10,        # 当前维度的健康评分
    "reason": str,        # 评分依据
    "suggestion": str     # 调整建议
}
```

现在需要决定每个分析器的**实现方式**。有三种选择：

### 选项 A：纯规则

所有分析器都用硬编码规则计算：
```python
if avg_completion >= 0.85:
    score = 9
    reason = "最近7天平均完成率85%,表现优秀"
    suggestion = "可以适当增加训练量"
```

**优势**：快速、低成本、可解释  
**劣势**：规则僵化，无法处理复杂场景（如"完成率高但用户反馈很累"）

### 选项 B：纯 LLM

所有分析器都调用 LLM 深度分析：
```python
prompt = f"用户最近7天完成率为{completion_rates}，请评估健康状况并给出0-10分"
response = llm.invoke(prompt)
```

**优势**：灵活、智能、能处理复杂情况  
**劣势**：
- **成本高**：5 个分析器并行，每次调整触发 5 次 LLM 调用
- **延迟高**：即使并行，也需要等待最慢的 LLM 调用完成
- **可解释性差**：LLM 的推理过程不透明

### 选项 C：混合模式

根据分析器的**复杂度**选择实现方式：
- **简单规则型**：用规则计算 score，LLM 生成 reason/suggestion
- **深度分析型**：完全用 LLM 分析

## 决策

采用**混合模式**，按分析器复杂度分配实现方式。

### 分配策略

| 分析器 | 实现方式 | 理由 |
|--------|----------|------|
| **completion_analyzer** | 规则 | 完成率是明确的数值，规则即可计算：平均值 > 0.85 → score 9，0.7-0.85 → score 7，< 0.7 → score 5 |
| **fatigue_analyzer** | 规则 | 疲劳度是用户主观评分（1-5），直接映射：1-2 → score 9-10，3 → score 7，4-5 → score 3-5 |
| **sleep_analyzer** | 规则 | 睡眠时长和质量是明确数值，规则计算：≥7小时且质量≥4 → score 9，6-7小时 → score 7，<6小时 → score 5 |
| **injury_risk_analyzer** | LLM | 需要综合完成度、疲劳度、训练频率、历史伤病记录，逻辑复杂，LLM 更适合 |
| **body_metrics_analyzer** | LLM | 需要分析体重/体脂趋势，结合用户目标（增肌/减脂），判断是否需要调整计划 |

### 实现示例

#### 规则型（completion_analyzer）

```python
def analyze_completion(completion_rates: List[float]) -> AnalyzerOutput:
    avg = sum(completion_rates) / len(completion_rates)
    
    # 规则计算 score
    if avg >= 0.85:
        score = 9
        base_reason = "最近7天平均完成率{:.0%}，表现优秀".format(avg)
    elif avg >= 0.7:
        score = 7
        base_reason = "最近7天平均完成率{:.0%}，表现良好".format(avg)
    else:
        score = 5
        base_reason = "最近7天平均完成率{:.0%}，略显吃力".format(avg)
    
    # LLM 生成 reason 和 suggestion（可选，MVP 阶段可用模板）
    prompt = f"{base_reason}。请用一句话解释原因，并给出调整建议。"
    llm_output = llm.invoke(prompt)
    
    return AnalyzerOutput(
        score=score,
        reason=llm_output.reason or base_reason,
        suggestion=llm_output.suggestion
    )
```

#### LLM 型（injury_risk_analyzer）

```python
def analyze_injury_risk(context: Dict) -> AnalyzerOutput:
    prompt = f"""
    分析用户的伤病风险（0-10分，0=无风险，10=高风险）：
    
    数据：
    - 最近7天完成率：{context['completion_rates']}
    - 最近7天疲劳度：{context['fatigue_scores']}
    - 连续训练天数：{context['consecutive_days']}
    - 历史伤病：{context.get('injury_history', '无')}
    - 某动作持续完成率低：{context.get('struggling_exercises', [])}
    
    请输出 JSON 格式：
    {{
        "score": <0-10>,
        "reason": "<评分依据>",
        "suggestion": "<调整建议>"
    }}
    """
    
    response = llm.invoke(prompt)
    return parse_json(response)
```

### MVP 简化策略

为了在 2 周内完成，规则型分析器的 reason/suggestion 可以先用**模板**，不调用 LLM：

```python
SUGGESTION_TEMPLATES = {
    "high_completion": "可以适当增加训练强度或组数",
    "medium_completion": "保持当前训练计划，继续巩固",
    "low_completion": "建议降低10-15%训练量，避免过度疲劳"
}
```

后续迭代时再引入 LLM 生成个性化文案。

## 后果

### 优势

1. **成本优化**
   - 只有 2 个分析器（injury_risk + body_metrics）调用 LLM
   - 相比全 LLM 方案，成本降低 60%

2. **延迟降低**
   - 规则计算瞬时完成（< 10ms）
   - 并行执行时，总延迟取决于最慢的 LLM 调用（injury_risk 或 body_metrics）
   - 预计总延迟 1-2 秒（可接受）

3. **可维护性**
   - 规则型分析器易于测试和调试
   - LLM 型分析器的 Prompt 可独立迭代优化

4. **可解释性**
   - 规则型分析器的推理过程透明（如"完成率85% → score 9"）
   - LLM 型分析器的复杂推理由 LLM 生成自然语言解释

### 权衡

1. **规则维护**
   - 规则型分析器需要人工调优阈值（如完成率多少算"优秀"）
   - 后续可能需要 A/B 测试调整规则

2. **一致性问题**
   - 规则型分析器的输出是确定性的
   - LLM 型分析器的输出可能有随机性（temperature > 0）
   - **缓解方案**：injury_risk 和 body_metrics 使用 temperature=0 保证稳定性

3. **MVP 阶段限制**
   - 规则型分析器使用模板生成 suggestion，可能不够个性化
   - 后续迭代时可引入轻量级 LLM 调用（如 Haiku）优化文案

## 备选方案

### 方案 A：全部使用规则

**未采用原因**：
- injury_risk 和 body_metrics 的逻辑太复杂，规则无法覆盖所有情况
- 技术亮点不足，无法展示 LLM 深度分析能力

### 方案 B：全部使用 LLM

**未采用原因**：
- 成本高：每次调整触发 5 次 LLM 调用（并行但仍需付费）
- 延迟高：即使并行，也需要等待最慢的调用完成
- 过度设计：completion/fatigue/sleep 是简单数值计算，用 LLM 是浪费

### 方案 C：动态选择（根据用户套餐）

如果用户是付费会员，全部用 LLM；如果是免费用户，全部用规则。

**未采用原因**：
- 项目是 BYOK 架构，用户自带 API Key，没有"付费会员"概念
- 增加复杂度，且 MVP 阶段不需要

## 相关决策

- [ADR-0001](0001-five-way-parallel-analyzers.md) - 5 路并行分析器架构
