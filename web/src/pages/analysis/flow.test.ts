import { describe, expect, it } from "vitest"

import { buildAnalysisJourney } from "./flow"

describe("buildAnalysisJourney", () => {
  it("keeps upload active before a photo is selected", () => {
    const journey = buildAnalysisJourney({
      hasImage: false,
      analyzing: false,
      hasResult: false,
      planGenerating: false,
      hasPlan: false,
    })

    expect(journey.stages.map((stage) => stage.status)).toEqual([
      "active",
      "pending",
      "pending",
      "pending",
    ])
    expect(journey.primaryAction).toBeNull()
  })

  it("guides the user to generate a plan after analysis completes", () => {
    const journey = buildAnalysisJourney({
      hasImage: true,
      analyzing: false,
      hasResult: true,
      planGenerating: false,
      hasPlan: false,
    })

    expect(journey.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "completed",
      "active",
      "pending",
    ])
    expect(journey.primaryAction?.label).toBe("生成专属训练计划")
    expect(journey.secondaryAction).toBeNull()
  })

  it("unlocks plan and training entry after a plan exists", () => {
    const journey = buildAnalysisJourney({
      hasImage: true,
      analyzing: false,
      hasResult: true,
      planGenerating: false,
      hasPlan: true,
    })

    expect(journey.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "completed",
      "completed",
      "active",
    ])
    expect(journey.primaryAction?.label).toBe("查看训练计划")
    expect(journey.secondaryAction?.label).toBe("进入 AI 陪练")
  })
})
