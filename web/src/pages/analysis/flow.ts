export type JourneyStageStatus = "pending" | "active" | "completed"

export interface JourneyStage {
  key: "upload" | "analyze" | "plan" | "train"
  label: string
  description: string
  status: JourneyStageStatus
}

export interface JourneyAction {
  label: string
  hint: string
  target: "generate-plan" | "view-plan" | "go-coach"
}

export interface BuildAnalysisJourneyInput {
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

/** Derive the analysis-to-training journey state from page-level booleans. */
export function buildAnalysisJourney(input: BuildAnalysisJourneyInput): AnalysisJourney {
  const { hasImage, analyzing, hasResult, planGenerating, hasPlan } = input

  const uploadStatus: JourneyStageStatus = hasImage || analyzing || hasResult ? "completed" : "active"
  const analyzeStatus: JourneyStageStatus =
    hasResult ? "completed" : analyzing ? "active" : hasImage ? "pending" : "pending"
  const planStatus: JourneyStageStatus =
    hasPlan ? "completed" : planGenerating ? "active" : hasResult ? "active" : "pending"
  const trainStatus: JourneyStageStatus = hasPlan ? "active" : "pending"

  if (hasPlan) {
    return {
      title: "分析已经接入训练链路",
      description: "结果已同步到训练计划，可以直接进入训练执行。",
      stages: [
        { key: "upload", label: "上传照片", description: "已提交分析照片", status: uploadStatus },
        { key: "analyze", label: "AI 分析", description: "已生成体型判断", status: analyzeStatus },
        { key: "plan", label: "生成计划", description: "已生成本周训练计划", status: planStatus },
        { key: "train", label: "开始训练", description: "现在可以进入计划或陪练", status: trainStatus },
      ],
      primaryAction: {
        label: "查看训练计划",
        hint: "继续查看本次分析对应的训练安排",
        target: "view-plan",
      },
      secondaryAction: {
        label: "进入 AI 陪练",
        hint: "带着分析结果直接进入训练指导",
        target: "go-coach",
      },
    }
  }

  if (hasResult || planGenerating) {
    return {
      title: planGenerating ? "正在把分析接入训练计划" : "分析已完成，下一步生成训练计划",
      description: planGenerating
        ? "系统正在根据这次体型分析生成训练安排。"
        : "不要停在结果页，直接把分析结论转成可执行训练。",
      stages: [
        { key: "upload", label: "上传照片", description: "已提交分析照片", status: uploadStatus },
        { key: "analyze", label: "AI 分析", description: "已生成体型判断", status: analyzeStatus },
        {
          key: "plan",
          label: "生成计划",
          description: planGenerating ? "正在生成专属训练计划" : "根据分析结果生成训练计划",
          status: planStatus,
        },
        { key: "train", label: "开始训练", description: "计划完成后进入训练执行", status: trainStatus },
      ],
      primaryAction: {
        label: "生成专属训练计划",
        hint: "将这次分析结果直接转成可执行训练方案",
        target: "generate-plan",
      },
      secondaryAction: null,
    }
  }

  if (analyzing) {
    return {
      title: "AI 正在分析你的体型",
      description: "分析完成后会直接引导你进入下一步训练安排。",
      stages: [
        { key: "upload", label: "上传照片", description: "已提交分析照片", status: uploadStatus },
        { key: "analyze", label: "AI 分析", description: "正在识别体型与肌群状态", status: analyzeStatus },
        { key: "plan", label: "生成计划", description: "等待分析结论", status: planStatus },
        { key: "train", label: "开始训练", description: "计划完成后进入训练执行", status: trainStatus },
      ],
      primaryAction: null,
      secondaryAction: null,
    }
  }

  return {
    title: "先完成体型分析",
    description: "上传照片后，系统会继续带你进入训练计划和训练执行。",
    stages: [
      { key: "upload", label: "上传照片", description: "选择一张清晰全身照", status: uploadStatus },
      { key: "analyze", label: "AI 分析", description: "识别体型与肌群状态", status: analyzeStatus },
      { key: "plan", label: "生成计划", description: "按分析结果产出训练安排", status: planStatus },
      { key: "train", label: "开始训练", description: "进入计划或 AI 陪练", status: trainStatus },
    ],
    primaryAction: null,
    secondaryAction: null,
  }
}
