# ADR-0004: 引入 Human-in-the-loop 机制处理风险决策

## 状态

已接受 (2026-10-27)

## 背景

[ADR-0001](0001-five-way-parallel-analyzers.md) 的 5 路并行分析器会综合评估用户状态，并自动调整训练计划。但某些情况下，**自动决策可能不合适**：

### 场景 1：伤病风险警告

injury_risk_analyzer 检测到高风险（score < 4），系统应该：
- **降低强度**？（用户可能不想停练）
- **更换动作**？（用户可能更愿意休息一天）
- **强制休息**？（用户可能认为"没那么严重"）

### 场景 2：目标冲突

body_metrics_analyzer 发现用户在减脂期但肌肉量下降，系统应该：
- **优先保肌**（增加力量训练，减少有氧）
- **继续减脂**（接受肌肉流失）
- **调整目标**（从减脂转为 recomp）

这类决策涉及**用户偏好**和**长期目标**，AI 自动决策可能与用户意图不符。

### 作为简历项目的考量

引入 Human-in-the-loop 机制可以：
1. **展示技术深度**：LangGraph 的 interrupt 功能是高级特性
2. **体现产品思维**：不是"全自动"，而是"智能辅助人类决策"
3. **避免责任风险**：健康相关决策由用户最终确认，AI 只提供建议

## 决策

在 **AdjustGraph** 的 decision_node 中引入 **Human-in-the-loop 机制**，使用 LangGraph 的 `interrupt` 功能。

### 触发条件

当以下任一条件满足时，暂停 Graph 执行，等待用户确认：

1. **伤病风险 ≥ 7 分**（injury_risk_analyzer 的 score ≤ 3）
2. **连续 3 次调整幅度 > 20%**（频繁大幅调整可能说明计划不合理）
3. **目标冲突**（体重/体脂变化与目标方向相反）

### 交互流程

```
decision_node
    ↓
检测到风险 → interrupt(reason="injury_risk_high")
    ↓
保存 Graph 状态到数据库
    ↓
前端弹窗显示：
    - 风险描述："连续6天高强度训练，膝关节可能过度使用"
    - 3个选项：
      1. 降低15%训练强度（推荐）
      2. 更换深蹲为腿举
      3. 我知道风险，继续当前计划
    ↓
用户选择后，前端发送请求：
POST /api/adjust/resume
{
    "graph_id": "adj_123",
    "user_choice": "reduce_intensity"
}
    ↓
后端恢复 Graph 执行，应用用户选择
    ↓
apply_changes
```

### 技术实现

#### 1. LangGraph Interrupt

```python
from langgraph.checkpoint import MemorySaver

# 定义 Graph 状态
class AdjustState(TypedDict):
    analyzers_output: List[AnalyzerOutput]
    merged_result: Dict
    user_choice: Optional[str]  # "reduce_intensity" | "swap_exercise" | "continue"
    
# decision_node
def decision_node(state: AdjustState):
    injury_risk = next(a for a in state["analyzers_output"] if a.name == "injury_risk")
    
    if injury_risk.score <= 3:  # 高风险
        # 触发 interrupt
        return {
            "interrupt_reason": "injury_risk_high",
            "options": [
                {"id": "reduce_intensity", "label": "降低15%训练强度（推荐）"},
                {"id": "swap_exercise", "label": "更换深蹲为腿举"},
                {"id": "continue", "label": "我知道风险，继续当前计划"}
            ]
        }
    
    # 无风险，直接决策
    return auto_decision(state)

# 创建 Graph 时启用 checkpointer
checkpointer = MemorySaver()
graph = StateGraph(AdjustState)
graph.add_node("decision", decision_node)
graph.add_conditional_edges("decision", should_interrupt)
compiled_graph = graph.compile(checkpointer=checkpointer)
```

#### 2. 前端弹窗（React）

```tsx
function RiskConfirmDialog({ risk, options, onConfirm }) {
  return (
    <Dialog open={true}>
      <DialogTitle>⚠️ 训练风险提示</DialogTitle>
      <DialogContent>
        <p>{risk.reason}</p>
        <p className="text-sm text-muted">
          建议：{risk.suggestion}
        </p>
      </DialogContent>
      <DialogActions>
        {options.map(opt => (
          <Button 
            key={opt.id}
            variant={opt.id === options[0].id ? "default" : "outline"}
            onClick={() => onConfirm(opt.id)}
          >
            {opt.label}
          </Button>
        ))}
      </DialogActions>
    </Dialog>
  )
}
```

#### 3. 后端恢复 API

```python
@router.post("/adjust/resume")
async def resume_adjustment(
    graph_id: str,
    user_choice: str,
    db: AsyncSession = Depends(get_db)
):
    # 从数据库加载 Graph 状态
    checkpoint = await load_checkpoint(graph_id)
    
    # 注入用户选择
    checkpoint["user_choice"] = user_choice
    
    # 恢复执行
    result = await compiled_graph.ainvoke(
        checkpoint,
        config={"configurable": {"thread_id": graph_id}}
    )
    
    return result
```

### 超时处理

如果用户 **5 分钟内未响应**，系统自动选择**最保守的选项**（如"降低强度"），并发送通知。

## 后果

### 优势

1. **技术深度提升**
   - LangGraph interrupt 是高级特性，展示状态管理和恢复能力
   - 涉及前后端协同、状态持久化、异步通信

2. **用户体验改善**
   - 用户对关键决策有控制权，不是"被 AI 支配"
   - 高风险情况下强制确认，避免意外受伤

3. **产品思维体现**
   - 不是"全自动黑盒"，而是"智能辅助决策"
   - 符合健康类应用的责任边界（AI 建议，人类决策）

4. **简历亮点**
   - 面试时可以讲："我实现了 Human-in-the-loop 机制，用 LangGraph 的 interrupt 功能暂停工作流，等待用户确认后恢复执行"

### 权衡

1. **实现复杂度增加**
   - 需要实现 Graph 状态持久化（数据库存储 checkpoint）
   - 需要前端弹窗组件 + WebSocket 或轮询检测 interrupt
   - 预计增加 2-3 天开发时间

2. **用户体验可能被打断**
   - 高风险时用户需要停下来做选择
   - **缓解方案**：只在真正高风险时触发（阈值严格设置），避免频繁打断

3. **状态管理复杂**
   - Graph 可能在多个节点 interrupt（如既有伤病风险，又有目标冲突）
   - **缓解方案**：MVP 阶段只在 decision_node 一个地方 interrupt

4. **超时逻辑**
   - 用户可能关闭页面后忘记确认
   - **缓解方案**：5 分钟超时自动选择保守方案 + 邮件/推送通知

## 备选方案

### 方案 A：完全自动决策

系统根据规则自动选择，不询问用户。

**未采用原因**：
- 伤病风险等决策涉及用户健康，全自动可能导致责任问题
- 技术深度不足，无法展示 LangGraph 高级特性

### 方案 B：事后确认

系统先应用调整，然后发通知让用户事后审批（不满意可撤销）。

**未采用原因**：
- 高风险决策应该**事前确认**，事后撤销可能已经造成伤害（如用户按照错误计划训练了一天）
- 撤销逻辑复杂（需要回滚计划、重新调整）

### 方案 C：批量确认

每周生成调整方案，发邮件给用户，用户回复确认后批量应用。

**未采用原因**：
- 实时性差，不符合"动态调整"的产品定位
- 邮件交互体验不如 Web 弹窗

### 方案 D：AI Agent 自主决策 + 解释

AI 自动决策，但生成详细的推理过程供用户查看。

**未采用原因**：
- 事后解释无法改变决策，用户可能不满意但已无法干预
- 不符合"人类主导，AI 辅助"的设计理念

## 相关决策

- [ADR-0001](0001-five-way-parallel-analyzers.md) - 5 路并行分析器架构
- [ADR-0003](0003-hybrid-analyzer-implementation.md) - injury_risk_analyzer 的输出会触发 interrupt
