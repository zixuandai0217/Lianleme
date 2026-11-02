import { describe, expect, it } from "vitest"

import { buildNextStepGuide, type NextStepSnapshot } from "@/lib/next-step"
import { buildAnalysisJourney } from "./flow"

const readyState: NextStepSnapshot = {
  hasApiKey: true,
  hasProfileBasics: true,
  hasBodyAnalysis: true,
  planLookup: "exists",
  hasCheckedIn: true,
}

const snapshot = (overrides: Partial<NextStepSnapshot> = {}): NextStepSnapshot => ({
  ...readyState,
  ...overrides,
})

const journey = (
  overrides: Partial<NextStepSnapshot> = {},
  page: Partial<{
    hasImage: boolean
    analyzing: boolean
    hasResult: boolean
    planGenerating: boolean
    hasPlan: boolean
  }> = {},
) => {
  const guide = buildNextStepGuide(snapshot(overrides))
  const hasPlan = (overrides.planLookup ?? readyState.planLookup) === "exists"
  return buildAnalysisJourney({
    guide,
    hasImage: page.hasImage ?? false,
    analyzing: page.analyzing ?? false,
    hasResult: page.hasResult ?? false,
    planGenerating: page.planGenerating ?? false,
    hasPlan: page.hasPlan ?? hasPlan,
  })
}

describe("buildAnalysisJourney 阶段状态来自共享 guide", () => {
  it("缺 Key 时四阶段全部 pending，主行动先回到配置 Key", () => {
    const result = journey({ hasApiKey: false, planLookup: "missing", hasCheckedIn: false })

    expect(result.stages.map((stage) => stage.status)).toEqual([
      "pending",
      "pending",
      "pending",
      "pending",
    ])
    expect(result.primaryAction?.label).toBe("配置 API Key")
    expect(result.primaryAction?.target).toBe("profile")
  })

  it("缺档案时不让分析阶段提前 active", () => {
    const result = journey({
      hasProfileBasics: false,
      hasBodyAnalysis: false,
      planLookup: "missing",
      hasCheckedIn: false,
    })

    expect(result.stages.map((stage) => stage.status)).toEqual([
      "pending",
      "pending",
      "pending",
      "pending",
    ])
    expect(result.primaryAction?.label).toBe("填写身体档案")
    expect(result.primaryAction?.target).toBe("body-data")
  })

  it("分析阶段 active 时只在分析内部细分上传与 AI 分析", () => {
    const beforePhoto = journey({ hasBodyAnalysis: false, planLookup: "missing", hasCheckedIn: false })
    expect(beforePhoto.stages.map((stage) => stage.status)).toEqual([
      "active",
      "pending",
      "pending",
      "pending",
    ])
    expect(beforePhoto.primaryAction).toBeNull()

    const analyzing = journey(
      { hasBodyAnalysis: false, planLookup: "missing", hasCheckedIn: false },
      { hasImage: true, analyzing: true },
    )
    expect(analyzing.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "active",
      "pending",
      "pending",
    ])
    expect(analyzing.primaryAction).toBeNull()
  })

  it("分析完成但没有计划时生成计划阶段 active，主行动为生成专属训练计划", () => {
    const result = journey(
      { planLookup: "missing", hasCheckedIn: false },
      { hasImage: true, hasResult: true },
    )

    expect(result.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "completed",
      "active",
      "pending",
    ])
    expect(result.primaryAction?.label).toBe("生成专属训练计划")
    expect(result.primaryAction?.target).toBe("generate-plan")
    expect(result.secondaryAction).toBeNull()
  })

  it("计划已存在但未打卡时训练阶段 active，主行动切换为查看训练计划", () => {
    const result = journey(
      { planLookup: "exists", hasCheckedIn: false },
      { hasImage: true, hasResult: true },
    )

    expect(result.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "completed",
      "completed",
      "active",
    ])
    expect(result.primaryAction?.label).toBe("查看训练计划")
    expect(result.primaryAction?.target).toBe("view-plan")
    expect(result.secondaryAction?.label).toBe("进入 AI 陪练")
  })

  it("全部完成时四阶段全部 completed，主行动仍可查看训练计划", () => {
    const result = journey({}, { hasImage: true, hasResult: true })

    expect(result.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "completed",
      "completed",
      "completed",
    ])
    expect(result.primaryAction?.label).toBe("查看训练计划")
  })

  it("计划无法判别时不给阶段进度，也不引导重建计划", () => {
    const result = journey({ planLookup: "unknown" })

    expect(result.stages.map((stage) => stage.status)).toEqual([
      "pending",
      "pending",
      "pending",
      "pending",
    ])
    expect(result.primaryAction?.label).toBe("查看今日安排")
    expect(result.primaryAction?.target).toBe("today")
    expect(result.title).not.toMatch(/失败|出错/)
  })

  it("生成计划进行中时计划阶段保持 active", () => {
    const result = journey(
      { planLookup: "missing", hasCheckedIn: false },
      { hasImage: true, hasResult: true, planGenerating: true },
    )

    expect(result.stages.find((stage) => stage.key === "plan")?.status).toBe("active")
    expect(result.primaryAction?.label).toBe("生成专属训练计划")
  })
})
