---
status: ready-for-agent
feature: adaptive-plan-adjustment
sources:
  - docs/adr/0001-five-way-parallel-analyzers.md
  - docs/adr/0003-hybrid-analyzer-implementation.md
  - docs/adr/0004-human-in-the-loop-risk-decisions.md
  - docs/plans/2026-06-02-production-readiness-roadmap.md
---

# Issue: 训练计划动态调整：5 路并行分析器、Merge Node 与风险决策的人机协同

## Problem Statement

用户练完一组打卡，系统只看一个数字：完成率。≥80% 就加量，<50% 就减量，其余不动。可现实里的训练不是这样运作的。有人咬牙完成了 100%，但那周每晚只睡五小时，系统照样把下周训练量再往上推 10-15%；有人连续六天高强度训练，膝关节已经在报警，系统只知道"你完成得不错"；有人某个动作的完成率持续偏低，可能是动作太难，也可能是器械总被占，系统一律当成"难度过高"减量。完成率是一个结果，不是一个状态。

更糟的是，用户根本看不见系统做了什么。调整在打卡后悄悄发生在后台，计划页只能看到"计划本体"，看不到"这次为什么变、变了多少、下周该练什么"。用户下一次进计划页，发现下周的组数多了一档，却无从追问理由；换个设备、隔两天再看，更是连"变过"这件事都没有痕迹。产品价值在这里断掉了：能力存在，但用户感知不到，也无法参与。

把健康相关的决策完全交给算法也不合适。真的检测到伤病风险时，是降低强度、换成对关节友好的动作、还是干脆休息一天？这不是模型能替用户拍的板——它涉及用户的偏好、目标和对自己身体的判断。系统如果单方面决定，用户要么被过度保护而烦躁，要么被"自动加量"推向受伤。反过来，如果为了安全把所有调整都做成人工确认，用户会在每次打卡后都被打断，动态调整这个产品定位就失去了意义。

所以这一版要同时解决三件事：用多维度评估替代单一完成率；把调整的理由和差异摊开给用户看；只在真正高风险或目标冲突时停下来，让用户在几个具体方案里拍板（Human-in-the-loop）。

## Solution

打卡后，系统从五个维度并行做一次"本周状态体检"：完成率、疲劳度、伤病风险、睡眠质量、体重/体脂趋势。每路分析器给出 0-10 的评分、一句理由和一条建议，其中三路是确定性规则瞬时算完，两路交给 LLM 做深度判断。所有结果汇总到 Merge Node，形成一份"本周状态小结"：整体健康分、各维度得分、被点亮的风险信号、以及最该被听见的几条理由。

小结进决策节点，映射成具体动作：加量 10-15%、减量 15-20%、换动作、插休息日、或保持。无论哪一种，用户都会在计划页看到一张说明卡——这次调整前后差在哪、哪个维度推动了这个决定。这不是日志，是给用户读的一段交代。

当合并结果里出现高风险信号（伤病风险评分过低、连续多次大幅调整、目标与身体变化方向相反）时，系统不再自动改计划，而是把这个调整挂成"待你决定"：给出风险描述和三个具体选项（含一个推荐的保守方案），由用户选一个，系统再落地。用户五分钟内没有回应，系统自动采用最保守的方案并把结果和理由留在计划页，让计划永远不卡在"等确认"。

这套能力在没有用户 Key、或者模型调用失败时也必须成立：规则维度照常出分，LLM 维度降级为模板文案并明确标记"这次没做深度分析"，调整本身仍然发生，用户看到的是朴素一点的解释，而不是一个报错。

## User Stories

1. 作为刚完成一次训练的用户，我想要系统不只盯着完成率，而是同时看我的疲劳、睡眠和体重趋势，以便它给出的加量或减量建议不会把我练废。
2. 作为连续高强度训练的用户，我想要系统在发现伤病风险时明确警告我，以便我不会因为"完成率高"被继续加量。
3. 作为只愿意填最少信息的用户，我想要不填疲劳和睡眠也能得到完整的调整结果，以便我不用先补完一张表单才能打卡。
4. 作为计划被调整过的用户，我想要看到每个维度的评分和理由，以便我知道这次决定到底是哪一项推动的。
5. 作为谨慎的用户，我想要在系统判定我有伤病风险时自己拍板选方案，以便最终决定权在我手上而不是算法手上。
6. 作为不想被打断的用户，我想要只有真正高风险时才弹窗确认，以便日常的小幅调整安静地发生。
7. 作为打卡后关掉页面去忙的用户，我想要系统在超时后自动采用最保守方案，以便我的下周计划不会一直卡在"待确认"。
8. 作为没有配置 API Key 的用户，我想要调整照样发生、只是解释文案朴素一些，以便我不会在打卡后看到一个"请先配置 Key"的报错。
9. 作为对自己身体有判断的用户，我想要能选择"我知道风险，继续当前计划"并被记录下来，以便系统不会在下一周反复劝同一件事。
10. 作为某周特别忙的用户，我想要系统在我完成率低时区分"计划太难"和"这周没时间"，以便它不会误把我的训练量砍掉。
11. 作为想复盘的用户，我想要在计划页看到本次调整前后的差异和原因，以便我理解我的计划是怎么一步步变过来的。
12. 作为减脂期的用户，我想要系统在我体重停滞、肌肉量下降时提醒目标冲突，以便我及时调整方向而不是白练两个月。
13. 作为被系统误判的用户，我想要对一次调整给出"不认同"的反馈，以便下次评估能更贴近我的真实状态。
14. 作为隐私敏感的用户，我想要我的睡眠、伤病和体重数据只用于当次评估，以便我敢如实填写而不担心被长期画像。
15. 作为在手机上打卡的用户，我想要风险确认弹窗在小屏上一眼能看完三个选项，以便我不会因为按钮挤在一起而误选。

## Implementation Decisions

### 1. Graph 拓扑与节点职责

采用 ADR-0001 的五路 fan-out / Merge / 决策 / 落地形状（来自 ADR-0001）：

```
analyze_input → [completion | fatigue | injury_risk | sleep | body_metrics] → merge_results → decision_node → apply_changes
```

- `analyze_input`：收集并裁剪评估所需输入，计算派生量（近 7 天完成率均值、连续训练天数、调整幅度历史），产出各分析器的输入切片。它不做判断，只做取材与缺省填充。
- 五个 Analyzer：彼此不共享可变状态，互不依赖，任意一路失败不影响其他四路。
- `merge_results`（Merge Node）：唯一把多路输出压成单一决策依据的地方。
- `decision_node`：把合并结果映射为调整动作；这里是全流程**唯一**允许触发 Human-in-the-loop 的位置。
- `apply_changes`：生成调整后的计划并落库，附带面向用户的说明数据。

### 2. 分析器契约（Analyzer 抽象）

每个 Analyzer 是一个独立单元，对外只暴露：`name`、实现方式（规则 / LLM）、以及统一输出：

```python
{ "score": 0-10, "reason": str, "suggestion": str }   # 来自 ADR-0001
```

本 spec 在此基础上补齐两个字段（ADR 未定义，此处决策）：

- `degraded: bool`——这一路是否降级运行（LLM 失败、数据缺失、Key 不可用）。
- `data_completeness: "full" | "partial" | "default"`——输入是真实数据、部分真实、还是完全用了缺省值。

**评分方向统一：`score` 一律是"健康评分"，10 最好、0 最差**（ADR-0001 的 schema 定义与 CONTEXT 的术语表都如此）。因此伤病风险高 ⇔ injury_risk 的健康评分低。伤病分析器内部若由模型给出的是"风险值"，必须在分析器内部转换成健康评分再出栈，全流程只在健康评分这一个语义上做判断。（ADR-0003 的 Prompt 示例把 injury_risk 描述成"0=无风险、10=高风险"，与 ADR-0004 的 `score <= 3` 判高风险相冲突；本 spec 按 ADR-0001 的 schema 与 ADR-0004 的判定统一为健康评分，理由与影响见 Further Notes。）

规则型分析与 LLM 型分析的分配严格照 ADR-0003：

| 分析器 | 实现 | 输入来源 |
| --- | --- | --- |
| completion | 规则 | 近 7 天完成率序列 |
| fatigue | 规则 | 用户自评（1-5） |
| sleep | 规则 | 睡眠时长 + 主观质量（1-5） |
| injury_risk | LLM | 完成度、训练频率、疲劳、历史伤病、长期低完成动作，可选姿态质量摘要 |
| body_metrics | LLM | 体重序列 + 体型分析历史 + 用户目标 |

规则阈值沿用 ADR-0003 的映射（完成率 ≥0.85→9、0.7-0.85→7、<0.7→5；疲劳 1-2→9-10、3→7、4-5→3-5；睡眠 ≥7h 且质量 ≥4→9、6-7h→7、<6h→5）。这些是**分析器内部**的评分映射，与决策节点的路由阈值是两件事，不得混用。

### 3. 并行执行语义

- 五路在同一层 fan-out，聚合前不设任何中间同步点；总耗时等于最慢一路，而非五路之和（ADR-0001 的核心动机）。
- 单路超时预算独立：规则路几乎瞬时；LLM 路给固定超时（量级：个位数秒），超时即按降级处理，不重试超过一次（ADR-0003 要求 temperature=0 保证稳定性，因此重试的边际价值低）。
- 单路异常必须被该路自己吞掉并转成"降级输出"，绝不让异常冒泡到 Merge 之前，否则并行编排退化成"任何一路抖动全线失败"。
- 五路输出顺序固定（按上表顺序），不依赖完成先后，避免同一用户两次调整的展示顺序抖动。

### 4. Merge Node 聚合规则

输入：五份分析器输出（每份带 score / degraded / data_completeness）。
输出（ADR 未定义，此处决策）：

```
merged_result = {
  overall_score: 0-10,          # 加权平均
  dimension_scores: {…},        # 五维得分，原样保留
  red_flags: [ {code, severity, evidence} ],
  top_reasons: [str],           # 最多 3 条，供解释卡片直接展示
  degraded_dimensions: [str],
  completeness: "full" | "partial" | "default"
}
```

- **聚合方式**：初期等权平均（ADR-0001 明确"初期采用简单平均，后续可引入领域知识"）。规则型与 LLM 型同权，不因实现方式不同而加权。
- **缺失与降级**：某路为 `default`（完全缺省）时，其权重不计入平均，并在 `degraded_dimensions` 中列出；`partial` 照常计入但标记。全五路都缺省属于不可发生状态，此时视为"评估不可用"，直接走保守动作（保持计划 + 提示补充数据），不触发 interrupt。
- **红标志（一票触发 interrupt，不与平均分混合）**，严格对应 ADR-0004 的三个触发条件：
  1. 伤病风险：injury_risk 健康评分 ≤ 3；
  2. 调整频率异常：连续 3 次调整幅度 > 20%；
  3. 目标冲突：体重/体脂变化方向与用户目标相反（例如减脂期体重上升、且肌肉评分未改善）。
- 红标志只决定"是否中断"，不直接决定"改多少"；具体动作仍由决策节点按合并分给出，或由用户选择覆盖。
- `top_reasons` 的选材规则：优先取红标志关联分析器的 reason，其次取与决策方向相反或极端的维度（分数最低/最高的一两条），避免把五段理由全量倒给用户。

### 5. 决策映射

- 路由只看 `overall_score`：≥7.5 → 加量（10-15%）；5.0-7.5 → 保持；<5.0 → 减量（15-20%）。幅度沿用现状与 ADR-0001 背景中的量级。
- 与现有完成率路由（0.8 / 0.5）的关系：完成率仍然是 completion 分析器的输入并影响合并分，但**不再单独决定方向**。为保持行为连续，当合并分指向的方向与完成率极值指向的方向冲突时，取更保守的一方（加量与保持冲突→保持；减量与保持冲突→减量）。（ADR 未定，此处决策。）
- 换动作与插休息日不作为整体路由的一档，而是分析器建议的落地形式：injury_risk 或 fatigue 的 `suggestion` 明确指向某个动作/休息时，决策节点在加量/减量之外附带"动作替换清单"或"休息日调整"，两者可叠加。
- 连续调整幅度需要被记录：每次落地的相对变化量入库，供红标志条件 2 判定，避免依赖内存状态。

### 6. interrupt / resume 契约

触发条件即上节三个红标志。触发后状态流转：

```
decision_node → 判定红标志 → 挂起（待用户选择） → resume(选项) → apply_changes
                                    └── 超时 → 自动采纳推荐选项 → apply_changes
```

挂起载荷（来自 ADR-0004 的语义，字段形状在此定稿）：

```
interrupt = {
  reason_code: "injury_risk_high" | "frequent_large_adjustment" | "goal_conflict",
  risk_level: "high",
  description: str,        # 一句话风险描述
  evidence: [str],         # 支撑证据（维度、数值、时间窗）
  options: [               # 固定 3 个，第一个是推荐（保守）项
    { id: "reduce_intensity" | "swap_exercise" | "continue", label, recommended: bool }
  ],
  expires_at: timestamp,
  proposed_adjustment: { direction, delta_percent, summary }
}
```

- 三个选项语义固定（来自 ADR-0004）：降低强度（推荐）、更换动作、知情继续。
- 恢复接口：`POST /api/plan/adjust/{adjustment_id}/resume`，请求体只有选项 id（ADR-0004 的 `POST /api/adjust/resume` 在本项目路由前缀下落到计划域；把 `graph_id` 换成对外稳定的 `adjustment_id`）。
- 幂等：同一 `adjustment_id` 重复提交同一选项返回同一结果；重复提交不同选项返回冲突语义且不覆盖已落地结果。
- 超时：5 分钟（来自 ADR-0004）。超时后自动采纳 `recommended` 选项并向用户回显"已按保守方案应用，可随时在计划页改成别的"。
- 超时的执行者：**读取时惰性判定 + 后台周期兜底**。任何一次查询（计划页、调整详情、撤销入口）都可以把已过期的调整收敛到终态；后台巡检保证没有用户访问时也会落地。二者必须共用一个"落地"操作，保证幂等。
- 唯一中断点：全流程只有决策后这一个 interrupt 位置（ADR-0004 明确 MVP 只在一处中断），不允许分析器各自弹窗。

### 7. 调整作为可查询的持久作业

调整是打卡后异步发生的，用户可能当场不在页面，也可能关掉页面再回来——所以"待用户选择"必须能被用户**发现**，而不是一个只存在于请求上下文里的弹窗。据此：

- 每次调整是一次持久作业，有稳定标识、状态（`evaluating | pending_choice | applied | expired_no_choice | failed`）与结果。`expired_no_choice` 表示"用户未在窗口内选择、已按推荐方案落地"，它与 `applied` 的唯一区别是决策者（`timeout_default` 而非 `user`）。
- 前端获取待确认项：`GET /api/plan/adjust/pending`（当前用户未决的调整，含 interrupt 载荷）；详情：`GET /api/plan/adjust/{adjustment_id}`（含五维小结、合并分、决策、前后差异）；时间线：`GET /api/plan/adjust/history`（倒序摘要，供计划页回看）。
- 作业的执行、租约与失败重试不属于本 spec：它与同批次的任务持久化 spec 共用同一条持久执行通道，本 spec 只消费该通道的可查询语义，不重复定义。
- 打卡响应绝不等待评估完成，也绝不因评估失败而回滚打卡（外部行为清单里有对应断言）。

### 8. 输入与输出形状

评估输入（`analyze_input` 的取材清单，缺项按缺省填充）：

```
completion_rates: [float]         # 近 7 天，缺省 → 空数组
fatigue_scores: [int 1-5]         # 缺省 → 3（来自 ADR-0001 的默认值约定）
sleep_hours / sleep_quality:      # 缺省 → 7.0h / 3
difficulty_ratings: [int 1-5]     # 现状已有，作为疲劳度的可用代理
consecutive_training_days: int
injury_history: [str] | none
struggling_exercises: [{name, completion_rate, weeks}]
weight_series: [{date, kg}]
body_fat_range_history: [str]
goal: "bulk" | "cut" | "maintain"
```

对外结果（`GET /api/plan/adjust/{adjustment_id}` 的响应形状）：

```json
{
  "adjustment_id": "adj_01J...",
  "status": "evaluating | pending_choice | applied | expired_no_choice | failed",
  "created_at": "…",
  "dimensions": [
    { "name": "completion", "score": 7, "reason": "…", "suggestion": "…",
      "source": "rule", "degraded": false, "data_completeness": "full" }
  ],
  "merged": { "overall_score": 6.4, "red_flags": [], "top_reasons": ["…"] },
  "decision": {
    "direction": "increase | decrease | keep",
    "delta_percent": 12,
    "exercise_swaps": [],
    "rest_day_change": null
  },
  "plan_diff": { "before_summary": "…", "after_summary": "…", "changed_days": [3, 5] },
  "interrupt": null,
  "client_message": "…",
  "degraded_dimensions": []
}
```

- `interrupt` 只在 `pending_choice` 时非空；`applied` 后保留用户选择摘要（`user_choice`、`chosen_by: "user" | "timeout_default"`），供计划页长期回看。
- 调整历史以列表形式提供，供计划页时间线使用；列表项不含完整维度细节，详情按需拉取。

### 9. 降级与成本控制

- **无 Key / 系统回退被禁用**：LLM 两路直接返回降级输出（健康评分取规则近似：例如伤病风险按完成度、连续天数、疲劳的组合规则粗算；体重趋势按线性方向判断），`degraded=true`，`reason` 用模板文案。全流程 200 返回、调整照常落地。**不得把"请配置 API Key"的凭据错误抛成 4xx**。
- **模型失败/超时/输出不可解析**：该路降级，其余继续；合并分按剩余权重归一。降级必须被显式记录并在前端标注"本次未做深度分析"，不静默。
- **成本上限**：一次调整最多 2 次 LLM 调用（ADR-0001/0003）；同一用户 24 小时内不重复做全量五维评估（复用上一次结果并把 `created_at` 展示给用户），除非用户手动触发"重新评估"。
- **节流**：打卡风暴（连续多次打卡/补打卡）合并成一次评估；短时间内的重复调整请求返回同一个作业。
- **LLM 输入最小化**：Prompt 只发送聚合摘要（7 天均值、序列长度、趋势方向、计数），不发送用户标识、邮箱、照片、以及完整逐日明细；temperature=0。

### 10. 隐私边界

- 疲劳、睡眠、伤病史、体重序列属于敏感健康数据：只用于当次评估与结果展示，不写入 LLM 长期记忆（当前架构也没有 memory store，需在实现时保持这一性质）。
- 落库的是"评估结论"（各维度分、理由、调整结果）与必要的最小原始值（红标志判定需要的幅度记录），不落"用户睡眠/伤病画像"。
- 日志只记录维度分数、降级标记、耗时与错误分类，不记录原始健康数值序列。
- 用户可见的 reason 文本会长期留在计划历史里，因此 Prompt 不得要求模型复述用户的具体伤病细节，只用泛化表述（如"膝关节负荷偏高"而非"你去年左膝半月板撕裂"）。

### 11. 前端展示契约

- 页面需要承载三块新信息：**本周状态小结**（五维评分 + 合并分 + 最该听的三条理由）、**调整时间线**（每次调整的方向、幅度、时间、由谁决定）、以及**风险确认模态**。本 spec 只定义这些信息的数据来源与状态机（何时可弹、何时只读、超时后如何呈现），页面信息架构与"为什么这样练"的整体解释区由计划解释性 spec 拥有，两者不得重复实现同一块 UI。
- 风险确认以模态呈现，三个选项平铺，推荐项有显式标记；关闭模态等同于"稍后决定"，页面顶部保留常驻提示以便回来处理。
- 所有文案遵循项目术语（完成率、疲劳度评分、伤病风险、Human-in-the-loop），调整说明属正式语言区，不使用 West Coast Slang（ADR-0006 明确计划/报告类保持正式）。

## Testing Decisions

### 好测试的标准

只断言外部可观测行为：HTTP 状态码、响应体里的维度列表与分数语义、状态流转（`pending_choice` → `applied`）、计划是否真的被改动、打卡响应是否不受影响。不断言 Graph 节点名、状态字段名、并行是用 `asyncio.gather` 还是别的、也不断言 LLM 被调用的确切 Prompt 文本。一个通过的测试应当能在"把五路分析器换成另一个实现、把 checkpointer 换成数据库实现、把 Merge 的权重表改掉"之后依然通过。

### 最高 seam：FastAPI 路由层

用 ASGI 传输的测试客户端起一个真实应用，依赖覆盖到隔离的临时数据库，并在这里把 **LLM 客户端**与**Graph 的执行体**替换成可控替身：

- LLM 替身返回固定 JSON（确定性、无网络、不消耗用户额度）。ADR-0003 的"规则+LLM 混合"天然给出无 LLM 也可测的规则分支，因此"降级"和"正常"两条路径都能在同一个 seam 上被稳定复现。
- Graph 执行体替身只在需要精确控制"挂起/恢复"节奏时使用（例如手动制造一个 `pending_choice` 作业），其余场景用真实 Graph + LLM 替身，让 fan-out/merge/decision 的真实逻辑被覆盖。

为什么不更低：本 spec 的风险全部是"用户能不能看到、能不能选、超时了会不会卡住、没 Key 会不会炸"，这些都能由请求/响应表达；更低的 seam（直接调节点函数）会把状态形状与节点拆分钉死，而 ADR 允许这些内部结构演进，且 Merge 的权重与阈值本来就是要迭代的部分。唯一需要下探的例外是**规则型分析器的评分映射**——它是纯函数、边界值密集（0.85/0.7、疲劳 3、睡眠 7h/6h），直接用表驱动单测覆盖边界，成本极低且不锁架构。LLM 型分析器不写"低层"测试，因为它没有可断言的确定性内部行为。

### 被测模块

1. 调整评估入口（触发一次评估 → 五维结果 + 合并分 + 决策）
2. 挂起/恢复路由（`pending` 查询、详情查询、`resume` 幂等、超时收敛）
3. Merge 聚合纯函数（权重归一、降级剔除、红标志识别、top_reasons 选材）
4. 五个分析器的规则分支（含缺省填充与方向语义）
5. 计划落地（调整结果写回计划、幅度记录、历史时间线）

### 必测行为清单

- 一次完整评估：响应里五维齐全、顺序稳定、每维都有 score/reason/suggestion。
- LLM 两路之一抛错：该维度 `degraded=true`，其余四维正常，决策与落地照常完成。
- 无用户 Key 且系统回退关闭：返回 200，`degraded_dimensions` 含两路，计划仍被调整；响应中不出现凭据错误码，也不出现"请配置 Key"文案。
- 全维缺省（新用户无任何历史）：不触发 interrupt，走保守动作，`completeness=default`。
- injury 健康评分 ≤ 3：状态为 `pending_choice`，`interrupt.options` 恰好 3 项且第一个 `recommended=true`；此阶段计划**未被修改**。
- 选择"知情继续"后恢复：计划保持原样，`chosen_by=user`，理由里记录用户选择。
- 选择"降低强度"后恢复：计划被下调，幅度落在声明区间内。
- 重复 resume：同选项二次提交返回同一结果，计划不被二次改动；不同选项提交被拒绝且不覆盖。
- 超时后 resume：返回"已按保守方案应用"的终态，计划已被保守方案改动一次且仅一次。
- 连续 3 次幅度 >20% 的历史 → 下次评估触发 interrupt（用历史构造，不依赖时间）。
- 打卡接口在上游评估失败时仍 200，打卡记录已落库（评估失败不污染打卡）。
- 调整历史列表能按时间倒序返回每次调整的方向与决策者（user / timeout_default）。

### 前端 seam

纯 TS 映射函数：五维结果 + 合并分 → 小结卡片视图模型（分数、色档、排序、文案）；调整结果 + interrupt 载荷 → 页面状态机（是否弹窗、推荐项高亮、倒计时剩余、超时后的只读态）。用 vitest 单测，不渲染页面。prior art 见下。

### 仓库内 prior art

- `backend/tests/test_coach_stream.py`：用假 Graph 类替换执行体、断言"上游失败时对外仍是可读结果"的写法，正是本 spec 降级路径的模板。
- `backend/tests/test_user_api_keys.py`：ASGI 传输 + 依赖覆盖 + 每文件独立临时 SQLite + 手搓 JWT 头，直接复用作路由层骨架；其中"monkeypatch 工厂 → 断言下游没有被真的调用"的写法用来验证"无 Key 时不会发起真实 LLM 调用"。
- `backend/tests/test_auth_guards.py`：越权与前置校验的骨架。
- `web/src/pages/analysis/flow.ts` 与 `flow.test.ts`：把页面的布尔量收敛成纯函数再单测，是"调整结果 → 页面状态机"该走的路。
- `backend/tests/test_coach_persona.py`：直接断言 CoachGraph 的 Prompt 是否带上风格约束（口语词、克制脏话、支持性语气），是"生成文案的风格要求该怎么被测试"的现成写法，适用于"调整说明保持正式语言"这条。

## Out of Scope

- ADR-0001 备选方案 B 的"生成 → 模拟结果 → 迭代优化"循环，以及任何长期效果预测。
- 在多处节点 interrupt（伤病风险与目标冲突同时出现时只弹一次，合并成一个决策）。
- 推送、邮件、短信通知；超时提醒只做站内（页面顶部常驻提示）。
- 计划生成的 Prompt 与模型选型、训练动作库的扩充。
- 用户对调整结果的"不认同"反馈如何进入模型迭代（只要求留下一条结构化反馈记录）。
- 打卡表单真的新增疲劳/睡眠两个字段（本 spec 只声明缺省行为；见 Further Notes 的前置依赖）。
- 调整的持久化执行通道本身（认领、租约、重试），由同批次的任务持久化 spec 定义。
- 前端视觉设计细节与动效；只要求信息结构与可达性（含移动端可读性）。
- 计费、配额、按套餐区分实现方式（ADR-0003 已否决分层策略）。

## Further Notes

- **ADR 未定，此处决策**：`score` 的语义与方向统一为"健康评分，越高越好"。依据是 ADR-0001 的 schema 注释与 ADR-0004 的 `injury_risk.score <= 3` 判定；ADR-0003 的 Prompt 示例把 injury_risk 写成"0=无风险、10=高风险"，与之冲突。落地方式是"分析器内部可自由采用风险语义，出栈前必须翻转成健康评分"，这样既不改 ADR-0003 的 Prompt 精神，也让下游只有一个方向。
- **ADR 未定，此处决策**：Merge 的聚合从"简单平均"具体化为"等权平均 + 缺失维度权重剔除 + 红标志旁路"。ADR-0001 只说初期简单平均、后续引入领域知识；把红标志设计成旁路（而不是加权项）是为了让"高风险必然中断"不受平均分稀释，这是 ADR-0004 安全语义的必要条件。
- **ADR 未定 / 内部不一致**：ADR-0004 一边用 `MemorySaver`（进程内存）示例，一边要求"保存 Graph 状态到数据库"。本 spec 要求 checkpoint 必须持久化（thread 标识 = 调整作业标识），否则进程重启后 `resume` 无处可恢复，超时兜底也无从谈起。实现可选用库自带的持久化 saver，或用"作业表 + 决策快照"自建；对测试与前端只暴露同一套路由语义。
- **ADR 未定，此处决策**：把"待确认的调整"提升为可查询的持久作业（`pending` 查询 + 详情 + resume），而不是纯前端弹窗。原因是触发点（打卡）与决策点（用户回来）在时间上分离；只做弹窗会让"用户当时不在页面"变成永久丢失。
- **现状缺口（ADR 假设的数据不存在）**：当前的打卡请求只有 `difficulty_rating`（自评难度 1-5），没有疲劳度与睡眠字段。ADR-0001 假设"打卡时主观上报疲劳 1-5""每日输入睡眠时长与质量"，这两项在代码里都不存在。因此本 spec 的缺省策略不是兜底而是常态：fatigue 用 `difficulty_rating` 作为代理（无值则 3），sleep 恒为缺省 3/7h 直到表单扩展。若产品要真正拿到这两维数据，需先做一次打卡表单扩展——这是本 spec 的前置依赖，未列入范围。
- **ADR 未定，此处决策**：决策路由阈值（7.5 / 5.0）与现状完成率阈值（0.8 / 0.5）并存时的冲突处理（取更保守方向）。理由：不希望在切换实现的那一周，用户看到计划方向反复横跳。
- **ADR 未定，此处决策**：24 小时评估去重窗口与"手动重新评估"入口。ADR 只约束单次最多 2 次 LLM 调用，没有约束频率；不做去重的话，补打卡行为会把成本放大数倍。
- **实现注意（现状代码的坑）**：打卡后的调整目前是"发射后不管"的后台协程，异常被吞、无结果可查；且调整发生在独立会话里，与打卡事务无关。这正好符合"打卡不被评估拖累"的要求，但意味着新实现必须自带可观测性，否则失败会完全静默。另：`AdjustGraph` 当前编译时没有 checkpointer，`interrupt` 无处挂；这是本 spec 最主要的实现前置。
- **库版本注意**：项目锁定 LangGraph 0.2.x。ADR-0004 示例里的 `from langgraph.checkpoint import MemorySaver` 在该版本下不成立（实际路径在 `langgraph.checkpoint.memory`），`interrupt()` 与 `Command(resume=...)` 的用法在该版本可用但细节与更新版本有差异。这属于实现细节澄清，不改变 ADR 的决策（仍是 LangGraph interrupt + checkpointer）。
- **跨 spec 对齐**：调整的持久执行通道、失败重试与观测事件字段由同批次的任务持久化 spec 与观测基线 spec 定义；姿态质量摘要作为 injury_risk 的**可选**输入，其字段契约由姿态纠错 spec 定义；计划页"为什么这样练"的解释区（目标、重点肌群来源、训练量摘要、历史调整理由的持久化与展示）由计划解释性 spec 拥有，本 spec 只保证提供五维小结、调整方向/幅度、决策者与 interrupt 载荷这几类数据。三项能力的边界：本 spec 谈"怎么评估与怎么让用户决定"，不谈姿态采集/成本节流（姿态 spec）与 3D 渲染（热力图 spec）。

> **迁移约定**：本 spec 引入了新的持久实体（调整作业与决策快照/checkpoint 持久化），属于改表，必须遵守全组统一约定——见 `analysis-task-persistence` spec 的「迁移与数据模型落地约定」一节（ORM 为唯一事实源、迁移与模型手写对齐、按交付追加 revision、可回滚、方言判断只出现在兼容层）。本 spec 不另立迁移约定。

## 相关文件

- [docs/adr/0001-five-way-parallel-analyzers.md](docs/adr/0001-five-way-parallel-analyzers.md) — 五路并行分析器与统一输出格式（Graph 形状的唯一来源）
- [docs/adr/0003-hybrid-analyzer-implementation.md](docs/adr/0003-hybrid-analyzer-implementation.md) — 规则/LLM 分配与规则阈值
- [docs/adr/0004-human-in-the-loop-risk-decisions.md](docs/adr/0004-human-in-the-loop-risk-decisions.md) — interrupt 触发条件、三选项与 5 分钟超时
- [docs/plans/2026-06-02-production-readiness-roadmap.md](docs/plans/2026-06-02-production-readiness-roadmap.md) — 3.2 节：调整已存在但用户感知不到的产品缺口
- [.scratch/plan-explainability/issue.md](.scratch/plan-explainability/issue.md) — 计划解释区的归属方（本 spec 只供数据，不重复实现该 UI）
- [.scratch/analysis-task-persistence/issue.md](.scratch/analysis-task-persistence/issue.md) — 调整所依赖的持久作业/执行器契约（本 spec 只消费其可查询语义）
- [backend/app/services/ai/adjust_graph.py](backend/app/services/ai/adjust_graph.py) — 现状：单维度完成率路由、无 Analyzer 抽象、无 checkpointer（第 14-63 行）
- [backend/app/services/ai/llm_factory.py](backend/app/services/ai/llm_factory.py) — BYOK 与系统回退、凭据错误类型（第 37-60 行）
- [backend/app/services/workout/workout_service.py](backend/app/services/workout/workout_service.py) — 打卡后 `asyncio.create_task` 的"发射后不管"触发（第 57-65、176-189 行）
- [backend/app/services/plan/plan_service.py](backend/app/services/plan/plan_service.py) — 调整结果写回计划的现有落地点（第 104-123 行）
- [backend/app/schemas/workout.py](backend/app/schemas/workout.py) — 现有打卡字段（只有 `difficulty_rating`，无疲劳/睡眠）
- [backend/app/models/record.py](backend/app/models/record.py) — 训练记录模型（完成率与自评难度）
- [backend/app/models/weight.py](backend/app/models/weight.py) — body_metrics 分析器的体重数据源
- [backend/app/api/plan.py](backend/app/api/plan.py) — 计划域路由前缀与权限守卫（resume 路由应落在这里）
- [backend/tests/test_coach_stream.py](backend/tests/test_coach_stream.py) — 假 Graph 类与降级断言（prior art）
- [backend/tests/test_user_api_keys.py](backend/tests/test_user_api_keys.py) — ASGI + 依赖覆盖 + 工厂替换（prior art）
- [web/src/pages/plan/index.tsx](web/src/pages/plan/index.tsx) — 计划页（小结卡片、调整时间线、风险弹窗的落点）
- [web/src/pages/analysis/flow.ts](web/src/pages/analysis/flow.ts) — 页面状态收敛为纯函数的既有范例
