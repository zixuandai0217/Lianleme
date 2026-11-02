import {
  stageStatusFor,
  type NextStepGuide,
  type NextStepStatus,
  type NextStepTarget,
} from "@/lib/next-step"

export type JourneyStageStatus = "pending" | "active" | "completed"

export interface JourneyStage {
  key: "upload" | "analyze" | "plan" | "train"
  label: string
  description: string
  status: JourneyStageStatus
}

export type JourneyActionTarget =
  | "generate-plan"
  | "view-plan"
  | "go-coach"
  | NextStepTarget

export interface JourneyAction {
  label: string
  hint: string
  target: JourneyActionTarget
}

export interface BuildAnalysisJourneyInput {
  /** 唯一的「当前缺哪一步」判定来源；本模块只做四阶段视觉投影。 */
  guide: NextStepGuide
  hasImage: boolean
  analyzing: boolean
  hasResult: boolean
  planGenerating: boolean
  hasPlan: boolean
}

export interface AnalysisJourney {
  title: string
  description: string
  stages: JourneyStage[]
  primaryAction: JourneyAction | null
  secondaryAction: JourneyAction | null
}

/**
 * 把共享引导的五步判定投影到分析页的四阶段闭环。
 *
 * 阶段状态只能取自 guide：前置步骤（Key/档案/分析）未满足时分析阶段不会是
 * active；上传与 AI 分析是「分析」阶段内部的视觉细分，因此只在分析阶段
 * 为 active 时按页面内进度继续细分，不引入第二套缺口判定。
 */
export function buildAnalysisJourney(input: BuildAnalysisJourneyInput): AnalysisJourney {
  const { guide, hasImage, analyzing, hasResult, planGenerating, hasPlan } = input

  const analysisStatus = stageStatusFor(guide, "analysis")
  const uploadStatus: JourneyStageStatus =
    analysisStatus === "completed"
      ? "completed"
      : analysisStatus === "active"
        ? hasImage || analyzing || hasResult
          ? "completed"
          : "active"
        : "pending"
  const analyzeStatus: JourneyStageStatus =
    analysisStatus === "completed"
      ? "completed"
      : analysisStatus === "active"
        ? analyzing || hasResult
          ? "active"
          : "pending"
        : "pending"
  const planStatus: JourneyStageStatus = planGenerating
    ? "active"
    : stageStatusFor(guide, "plan")
  const trainStatus: JourneyStageStatus = stageStatusFor(guide, "first-checkin")

  const stages: JourneyStage[] = [
    { key: "upload", label: "上传照片", description: hasResult ? "已提交分析照片" : "选择一张清晰全身照", status: uploadStatus },
    {
      key: "analyze",
      label: "AI 分析",
      description: analyzing ? "正在识别体型与肌群状态" : hasResult ? "已生成体型判断" : "识别体型与肌群状态",
      status: analyzeStatus,
    },
    {
      key: "plan",
      label: "生成计划",
      description: planGenerating
        ? "正在生成专属训练计划"
        : hasPlan
          ? "已生成本周训练计划"
          : "按分析结果产出训练安排",
      status: planStatus,
    },
    {
      key: "train",
      label: "开始训练",
      description: hasPlan ? "进入计划或 AI 陪练" : "计划完成后进入训练执行",
      status: trainStatus,
    },
  ]

  const primaryAction = resolvePrimaryAction(guide, hasPlan)
  const secondaryAction: JourneyAction | null = hasPlan
    ? { label: "进入 AI 陪练", hint: "带着分析结果直接进入训练指导", target: "go-coach" }
    : null

  if (guide.state === "unknown" || guide.currentStep === "api-key" || guide.currentStep === "profile") {
    return {
      title: guide.title,
      description: guide.description,
      stages,
      primaryAction,
      secondaryAction,
    }
  }

  if (hasPlan) {
    return {
      title: "分析已经接入训练链路",
      description: "结果已同步到训练计划，可以直接进入训练执行。",
      stages,
      primaryAction,
      secondaryAction,
    }
  }

  if (hasResult || planGenerating) {
    return {
      title: planGenerating ? "正在把分析接入训练计划" : "分析已完成，下一步生成训练计划",
      description: planGenerating
        ? "系统正在根据这次体型分析生成训练安排。"
        : "不要停在结果页，直接把分析结论转成可执行训练。",
      stages,
      primaryAction,
      secondaryAction,
    }
  }

  if (analyzing) {
    return {
      title: "AI 正在分析你的体型",
      description: "分析完成后会直接引导你进入下一步训练安排。",
      stages,
      primaryAction,
      secondaryAction,
    }
  }

  return {
    title: "先完成体型分析",
    description: "上传照片后，系统会继续带你进入训练计划和训练执行。",
    stages,
    primaryAction,
    secondaryAction,
  }
}

/** 主行动优先表达共享引导的当前步；分析步本身由下方上传区承担。 */
function resolvePrimaryAction(guide: NextStepGuide, hasPlan: boolean): JourneyAction | null {
  if (hasPlan) {
    return {
      label: "查看训练计划",
      hint: "继续查看本次分析对应的训练安排",
      target: "view-plan",
    }
  }

  if (guide.state === "daily") return null
  if (guide.state === "unknown") {
    return {
      label: guide.primaryAction.label,
      hint: guide.primaryAction.hint,
      target: guide.primaryAction.target,
    }
  }

  switch (guide.currentStep) {
    case "plan":
      return {
        label: "生成专属训练计划",
        hint: "将这次分析结果直接转成可执行训练方案",
        target: "generate-plan",
      }
    case "first-checkin":
      return {
        label: "查看今日训练",
        hint: "按今日安排训练并完成打卡",
        target: "today",
      }
    case "analysis":
      return null
    case "api-key":
    case "profile":
      return {
        label: guide.primaryAction.label,
        hint: guide.primaryAction.hint,
        target: guide.primaryAction.target,
      }
    default:
      return null
  }
}

/** 导出给测试与页面共用：阶段状态的可读文案。 */
export function journeyStatusLabel(status: NextStepStatus): string {
  return status === "completed" ? "已完成" : status === "active" ? "当前步骤" : "待完成"
}
