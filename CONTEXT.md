# 练了么 (Lianleme) - 领域上下文

## 项目概述

**练了么**是一个 AI 驱动的健身教练应用，提供体型分析、个性化训练计划、AI 陪练对话和体重追踪功能。

当前项目正在进行**简历项目优化**，目标是提升技术深度和工程质量，使其适合作为 **AI 应用工程师**岗位的作品集项目。优化重点：
- 强化 LangGraph 多 Agent 编排能力
- 引入实时姿态检测与动作纠错
- 增加 3D 可视化能力
- 提升训练计划调整的智能化程度

---

## 核心概念

### LangGraph 工作流

**LangGraph** 是 LangChain 的状态机编排框架，用于构建多步骤 AI 工作流。项目中有三类 Graph：

- **VisionGraph**：体型分析工作流（线性 DAG）
- **AdjustGraph**：训练计划动态调整工作流（条件分支 + 并行分析）
- **CoachGraph**：AI 陪练对话工作流（对话历史持久化）
- **PoseGraph**（会话与周期切分已落地，识别/评估待接入）：姿态纠错工作流；会话状态只存进程内存（ADR-0010）
- **WorkoutGraph**（待实现）：训练全流程编排工作流

### 体型分析系统

用户上传全身照片，通过多模态视觉 LLM（Qwen-VL）分析得出：
- **体型分类**：ectomorph（外胚层）/ mesomorph（中胚层）/ endomorph（内胚层）
- **体脂估算**：百分比区间（如 18-22%）
- **弱势肌群识别**：训练重点建议
- **肌肉评分**：各部位 0-10 分（用于热力图可视化）

### 训练计划调整

基于用户训练完成情况，动态调整训练计划强度。当前实现只基于**完成率**单一维度；优化版将采用 **5 路并行分析器**，综合考虑完成率、疲劳度、伤病风险、睡眠质量、体重/体脂趋势。

### 姿态检测

使用 **MediaPipe Pose** 提取人体关键点（33 个），通过 LLM 分析动作质量，实时提供纠错反馈。

### 多租户 LLM 架构

每个用户可配置自己的 OpenAI / 阿里云通义千问 API Key，经 AES-256-GCM 加密存储。系统提供可选的 Key 回退机制（`ALLOW_SYSTEM_LLM_FALLBACK`）。

---

## 术语表

### A

**AdjustGraph**
训练计划动态调整工作流。根据用户训练反馈（完成率、疲劳度等）自动调整下周计划的难度。

**Analyzer（分析器）**
AdjustGraph 中的并行节点，负责从特定维度评估用户状态。输出格式：`{name, score: 0-10, reason, suggestion, source: rule | llm, degraded, data_completeness: full | partial | default}`。五个维度：完成率、疲劳度、伤病风险、睡眠、体重/体脂趋势；缺省维度用 `default` 标记并排除在合并均分之外（规则见 [ADR-0009](docs/adr/0009-five-dimension-merge-and-direction.md)）。

### B

**BYOK (Bring Your Own Key)**
用户自带 API Key 的架构模式。练了么不提供中心化 LLM 服务，用户需自行配置供应商密钥。

### C

**CoachGraph**
AI 陪练对话工作流。加载用户最近 20 条对话历史，生成上下文感知的回复，支持流式输出（SSE）。

**Completion Rate（完成率）**
用户实际完成的训练组数 / 计划总组数。用于触发计划调整的核心指标。

### D

**Dynamic Adjustment（动态调整）**
根据用户表现自动修改训练计划的机制。触发时机：用户完成一次训练打卡后异步执行。

### F

**Fatigue Score（疲劳度评分）**
用户主观上报的疲劳程度，1-5 分。高疲劳时系统会降低训练强度或插入休息日。

### H

**Human-in-the-loop（人机协同）**
在关键决策点（如检测到伤病风险）暂停 Graph 执行，让用户选择处理方案后继续。使用 LangGraph 的 `interrupt` 机制实现。

### I

**Injury Risk（伤病风险）**
基于训练频率、完成度、疲劳度、姿态检测数据综合评估的受伤概率。高风险时触发人工确认流程。

### K

**Keypoint（关键点）**
MediaPipe Pose 输出的人体骨骼点坐标，共 33 个，包括面部、上肢、躯干、下肢。用于姿态分析。

### M

**MediaPipe Pose**
Google 开源的轻量级姿态检测库，可在浏览器/移动端实时运行。输出 33 个人体关键点的 3D 坐标。

**Merge Node（合并节点）**
并行分析器执行后的汇总节点，聚合多个分析器的输出，生成统一的决策依据。

**Motion Cycle（动作周期）**
一次完整动作的时间跨度（如深蹲下蹲 → 站起 = 一个周期，2-4 秒）。姿态纠错以周期为单位进行。

**Muscle Heatmap（肌肉热力图）**
3D 人体模型上根据肌肉评分（0-10）渲染的材质发光效果。低分区域暗淡，高分区域发光明亮。

### P

**PoseGraph**
姿态分析工作流。输入 MediaPipe 关键点序列，LLM 自动识别动作类型并输出质量评估和纠错建议。

### R

**Request ID（请求关联标识）**
一次请求的稳定标识，入口生成或沿用（`X-Request-ID`），贯穿日志、响应头与后台任务，用于把「用户说坏了」定位到具体那次执行。

**Rhubarb Lip Sync**
开源的语音唇形同步工具。分析 TTS 音频生成口型时间轴（viseme A-H），用于数字教练的口型动画。

### Q

**Quality Gate（质量门）**
一条命令给出「当前是否达标」的结论：前端类型检查 / lint / 单测、后端静态检查 / 单测，完整档再加主链路 smoke 与构建自检；任何一步红都返回非零退出码。

### S

**SSE (Server-Sent Events)**
单向服务器推送技术，用于实现 AI 对话的流式响应（逐 token 推送）。

**SSE Event Stream（结构化事件流）**
陪练流式输出的 v1 协议：每帧单行 JSON，类型判别在帧内 `type` 上，固定六类事件（`turn_started` / `message_chunk` / `state` / `actions` / `error` / `done`），`done` 是唯一终结帧；见 ADR-0007。

**Structured Logging（结构化日志）**
一条日志一行 JSON，字段名由常量集中定义、禁止同义别名，请求级失败带请求关联标识与错误分类；见 ADR-0008。

**System Fallback（系统回退）**
当用户未配置 API Key 时，使用系统级密钥作为回退方案。生产环境可通过环境变量禁用。

### T

**TTS (Text-to-Speech)**
文本转语音服务。当前使用阿里云通义千问 Voice Design API，支持系统音色和用户自定义音色。

### V

**VisionGraph**
体型分析工作流。三节点 DAG：vision（多模态 LLM 分析）→ parse（结构化输出解析）→ 保存结果。

### W

**West Coast Slang（西海岸俚语）**
AI 教练的口语化风格，模仿美国西海岸健身文化用语（如 "yo bro", "let's go", "homie"）。应用于所有 AI 生成的反馈文本（CoachGraph、PoseGraph、训练完成总结、计划调整理由等）。

**WorkoutGraph**
训练全流程编排工作流。包含加载计划、动作执行循环、姿态检测、纠错反馈、完成总结、触发调整等节点。

---

## 数据流概览

```
用户上传照片
  ↓
VisionGraph 体型分析
  ↓
生成个性化训练计划
  ↓
WorkoutGraph 训练执行
  ├→ PoseGraph 实时姿态检测
  ├→ CoachGraph AI 陪练对话
  └→ 完成打卡
  ↓
AdjustGraph 动态调整
  ├→ 5 路并行分析器
  ├→ Human-in-the-loop（风险决策）
  └→ 生成调整后计划
```

---

## 相关决策

关键架构决策记录在 `docs/adr/` 目录：
- [ADR-0001](docs/adr/0001-five-way-parallel-analyzers.md) - 5 路并行分析器架构
- [ADR-0002](docs/adr/0002-mediapipe-pose-detection.md) - 选择 MediaPipe 进行姿态检测
- [ADR-0003](docs/adr/0003-hybrid-analyzer-implementation.md) - 混合模式分析器（规则+LLM）
- [ADR-0004](docs/adr/0004-human-in-the-loop-risk-decisions.md) - 风险决策的人机协同机制
- [ADR-0005](docs/adr/0005-threejs-3d-muscle-heatmap.md) - Three.js 3D 肌肉热力图
- [ADR-0006](docs/adr/0006-west-coast-coach-voice.md) - 西海岸口语风格教练设计
- [ADR-0007](docs/adr/0007-coach-event-protocol.md) - 陪练流式输出改用结构化事件协议
- [ADR-0008](docs/adr/0008-observability-contract.md) - 运行观测契约（请求关联、结构化日志、脱敏）
- [ADR-0009](docs/adr/0009-five-dimension-merge-and-direction.md) - 五维合并与方向决策规则
