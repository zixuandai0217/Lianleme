/* 首用「下一步」判定：把「用户现在缺哪一步」收敛成一份无副作用的纯函数。 */

import type { PlanLookup } from "@/api/types"

/** 首用状态快照：全部来自现有接口，判定只依赖它。 */
export interface NextStepSnapshot {
  hasApiKey: boolean
  hasProfileBasics: boolean
  hasBodyAnalysis: boolean
  planLookup: PlanLookup
  hasCheckedIn: boolean
}

export type NextStepKey = "api-key" | "profile" | "analysis" | "plan" | "first-checkin"
export type NextStepStatus = "pending" | "active" | "completed"
export type NextStepTarget = "profile" | "body-data" | "analysis" | "plan" | "today"
export type NextStepState = "guide" | "daily" | "unknown"

/** 页面无关的意图到路由的映射：判定不感知路由，由页面取用。 */
export const NEXT_STEP_ROUTES: Record<NextStepTarget, string> = {
  profile: "/profile",
  "body-data": "/weight",
  analysis: "/analysis",
  plan: "/plan",
  today: "/",
}

export interface NextStepAction {
  label: string
  hint: string
  target: NextStepTarget
}

export interface NextStepStage {
  key: NextStepKey
  title: string
  description: string
  status: NextStepStatus
}

export interface NextStepGuide {
  state: NextStepState
  title: string
  description: string
  currentStep: NextStepKey | null
  stages: NextStepStage[]
  primaryAction: NextStepAction
  /** 只在日常循环态出现：档案缺失的次要提示，不改变主行动。 */
  secondaryHint: string | null
}

interface StageCopy {
  title: string
  description: string
}

const STAGE_COPY: Record<NextStepKey, StageCopy> = {
  "api-key": { title: "配置 AI Key", description: "使用自己的供应商密钥" },
  profile: { title: "补全身体档案", description: "健身目标与训练经验" },
  analysis: { title: "完成体型分析", description: "上传全身照得到体型分类" },
  plan: { title: "生成训练计划", description: "按分析排出本周安排" },
  "first-checkin": { title: "完成第一次打卡", description: "按安排练完并记录" },
}

const STAGE_ORDER: NextStepKey[] = ["api-key", "profile", "analysis", "plan", "first-checkin"]

const STEP_GUIDES: Record<
  NextStepKey,
  { title: string; description: string; action: NextStepAction }
> = {
  "api-key": {
    title: "先配置自己的 AI Key",
    description: "分析和计划生成都依赖你自己的 Key，配置后这些页面才能使用。",
    action: { label: "配置 API Key", hint: "打开个人资料", target: "profile" },
  },
  profile: {
    title: "补全身体档案",
    description: "填写健身目标与训练经验，分析与计划会按这些信息调整。",
    action: { label: "填写身体档案", hint: "在身体数据页填写", target: "body-data" },
  },
  analysis: {
    title: "完成一次体型分析",
    description: "上传一张全身照，得到体型分类与需要加强的部位。",
    action: { label: "去做体型分析", hint: "上传全身照", target: "analysis" },
  },
  plan: {
    title: "生成本周训练计划",
    description: "按这次分析排出一周的训练安排。",
    action: { label: "生成训练计划", hint: "按分析结果生成", target: "plan" },
  },
  "first-checkin": {
    title: "完成第一次训练打卡",
    description: "按今天的安排练完并打卡，之后就按节奏走。",
    action: { label: "查看今日训练", hint: "练完记得打卡", target: "today" },
  },
}

const DAILY_GUIDE = {
  title: "今天可以开始训练了",
  description: "档案、分析与计划都已就绪，按今日安排练就行。",
  primaryAction: {
    label: "查看今日训练",
    hint: "今天的安排在下方",
    target: "today",
  } satisfies NextStepAction,
}

const UNKNOWN_GUIDE = {
  title: "先看看今天的安排",
  description: "暂时没能确认训练计划的状态，先按今日内容来。",
  primaryAction: {
    label: "查看今日安排",
    hint: "今天的内容在下方",
    target: "today",
  } satisfies NextStepAction,
}

const PROFILE_HINT = "补全身体档案后，下周计划会更贴合你的目标。"

function isSatisfied(key: NextStepKey, snapshot: NextStepSnapshot): boolean {
  switch (key) {
    case "api-key":
      return snapshot.hasApiKey
    case "profile":
      return snapshot.hasProfileBasics
    case "analysis":
      return snapshot.hasBodyAnalysis
    case "plan":
      return snapshot.planLookup === "exists"
    case "first-checkin":
      return snapshot.hasCheckedIn
  }
}

/** 判定表：自上而下命中即返回；计划存在性无法判别时由调用方先行处理。 */
function decideCurrentStep(snapshot: NextStepSnapshot): NextStepKey | null {
  if (!snapshot.hasApiKey) return "api-key"
  if (!snapshot.hasBodyAnalysis && !snapshot.hasProfileBasics) return "profile"
  // 计划已存在而分析为空属于历史数据，不回退到分析步，避免主行动与现状冲突。
  if (!snapshot.hasBodyAnalysis && snapshot.planLookup !== "exists") return "analysis"
  if (snapshot.planLookup === "missing") return "plan"
  if (!snapshot.hasCheckedIn) return "first-checkin"
  return null
}

function buildStages(currentStep: NextStepKey, snapshot: NextStepSnapshot): NextStepStage[] {
  const currentIndex = STAGE_ORDER.indexOf(currentStep)

  return STAGE_ORDER.map((key, index) => {
    const status: NextStepStatus =
      key === currentStep
        ? "active"
        : isSatisfied(key, snapshot) && index < currentIndex
          ? "completed"
          : "pending"

    return { key, ...STAGE_COPY[key], status }
  })
}

/**
 * 根据首用状态快照给出唯一的当前步与唯一主行动。
 *
 * 计划查询无法判别（unknown）时进入中性未知态：不给步骤进度，也不引导用户
 * 去重建计划——重新生成会归档当前计划，误判的代价由用户承担。
 */
export function buildNextStepGuide(snapshot: NextStepSnapshot): NextStepGuide {
  if (snapshot.planLookup === "unknown") {
    return {
      state: "unknown",
      ...UNKNOWN_GUIDE,
      currentStep: null,
      stages: [],
      secondaryHint: null,
    }
  }

  const currentStep = decideCurrentStep(snapshot)

  if (!currentStep) {
    return {
      state: "daily",
      ...DAILY_GUIDE,
      currentStep: null,
      stages: [],
      secondaryHint: snapshot.hasProfileBasics ? null : PROFILE_HINT,
    }
  }

  const stepGuide = STEP_GUIDES[currentStep]

  return {
    state: "guide",
    title: stepGuide.title,
    description: stepGuide.description,
    currentStep,
    stages: buildStages(currentStep, snapshot),
    primaryAction: stepGuide.action,
    secondaryHint: null,
  }
}

/**
 * 页面投影辅助：从共享 guide 读取指定阶段状态。
 *
 * daily 表示全部前置条件已满足（全部 completed）；unknown 表示无法判别
 * （不显示进度，全部 pending）。页面不允许绕开 guide 自行重新判定。
 */
export function stageStatusFor(
  guide: NextStepGuide,
  key: NextStepKey,
): NextStepStatus {
  if (guide.state === "daily") return "completed"
  if (guide.state === "unknown") return "pending"
  return guide.stages.find((stage) => stage.key === key)?.status ?? "pending"
}
