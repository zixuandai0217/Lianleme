/* 首用「下一步」判定的行为约束：判定表、未知态、状态自洽与纯度。 */
import { describe, expect, it } from "vitest"
import { NEXT_STEP_ROUTES, buildNextStepGuide, stageStatusFor, type NextStepSnapshot } from "@/lib/next-step"

const readyState: NextStepSnapshot = {
  hasApiKey: true,
  hasProfileBasics: true,
  hasBodyAnalysis: true,
  planLookup: "exists",
  hasCheckedIn: true,
}

// 以「全部就绪」为基线，按用例覆盖单个缺口，避免每例重复写五个字段。
const snapshot = (overrides: Partial<NextStepSnapshot> = {}): NextStepSnapshot => ({
  ...readyState,
  ...overrides,
})

describe("buildNextStepGuide 判定表", () => {
  it("没有 AI Key 时先引导配置 Key，即使档案、分析、计划、打卡都还缺", () => {
    const guide = buildNextStepGuide(
      snapshot({
        hasApiKey: false,
        hasProfileBasics: false,
        hasBodyAnalysis: false,
        planLookup: "missing",
        hasCheckedIn: false,
      }),
    )

    expect(guide.state).toBe("guide")
    expect(guide.currentStep).toBe("api-key")
    expect(guide.primaryAction.target).toBe("profile")
    expect(guide.stages.map((stage) => stage.status)).toEqual([
      "active",
      "pending",
      "pending",
      "pending",
      "pending",
    ])
  })

  it("缺 Key 时主行动从不指向会被门禁拦回的页面", () => {
    const guide = buildNextStepGuide(snapshot({ hasApiKey: false, planLookup: "missing" }))

    expect(["profile", "body-data"]).toContain(guide.primaryAction.target)
  })

  it("档案与体型分析都缺时先补档案，再去做分析", () => {
    const guide = buildNextStepGuide(
      snapshot({ hasProfileBasics: false, hasBodyAnalysis: false, planLookup: "missing" }),
    )

    expect(guide.currentStep).toBe("profile")
    expect(guide.primaryAction.target).toBe("body-data")
  })

  it("有档案但没做过体型分析时引导去做分析", () => {
    const guide = buildNextStepGuide(
      snapshot({ hasBodyAnalysis: false, planLookup: "missing" }),
    )

    expect(guide.state).toBe("guide")
    expect(guide.currentStep).toBe("analysis")
    expect(guide.primaryAction.target).toBe("analysis")
    expect(guide.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "completed",
      "active",
      "pending",
      "pending",
    ])
  })

  it("档案与分析就绪但没有计划时引导生成计划", () => {
    const guide = buildNextStepGuide(snapshot({ planLookup: "missing" }))

    expect(guide.currentStep).toBe("plan")
    expect(guide.primaryAction.target).toBe("plan")
    expect(guide.stages.map((stage) => stage.status)).toEqual([
      "completed",
      "completed",
      "completed",
      "active",
      "pending",
    ])
  })

  it("有计划但还没打过卡时引导完成第一次打卡", () => {
    const guide = buildNextStepGuide(snapshot({ hasCheckedIn: false }))

    expect(guide.currentStep).toBe("first-checkin")
    expect(guide.primaryAction.target).toBe("today")
    expect(guide.stages.at(-1)?.status).toBe("active")
  })

  it("全部就绪后进入日常循环态，不再显示引导步骤", () => {
    const guide = buildNextStepGuide(snapshot())

    expect(guide.state).toBe("daily")
    expect(guide.currentStep).toBeNull()
    expect(guide.stages).toEqual([])
    expect(guide.primaryAction.target).toBe("today")
  })
})

describe("buildNextStepGuide 附则", () => {
  it("日常循环下只把档案缺失降级为次要提示，不改变主行动", () => {
    const guide = buildNextStepGuide(snapshot({ hasProfileBasics: false }))

    expect(guide.state).toBe("daily")
    expect(guide.primaryAction.target).toBe("today")
    expect(guide.secondaryHint).toBeTruthy()
  })

  it("日常循环且档案齐全时没有次要提示", () => {
    const guide = buildNextStepGuide(snapshot())

    expect(guide.secondaryHint).toBeNull()
  })

  it("计划已存在但体型分析为空时不回退到分析步", () => {
    const withOpenCheckin = buildNextStepGuide(
      snapshot({ hasBodyAnalysis: false, hasCheckedIn: false }),
    )
    const finished = buildNextStepGuide(snapshot({ hasBodyAnalysis: false }))

    expect(withOpenCheckin.currentStep).not.toBe("analysis")
    expect(withOpenCheckin.currentStep).toBe("first-checkin")
    expect(finished.state).toBe("daily")
  })
})

describe("buildNextStepGuide 未知态", () => {
  it("计划查询无法判别时进入中性未知态，不给步骤进度", () => {
    const guide = buildNextStepGuide(snapshot({ planLookup: "unknown" }))

    expect(guide.state).toBe("unknown")
    expect(guide.currentStep).toBeNull()
    expect(guide.stages).toEqual([])
    expect(guide.primaryAction.target).toBe("today")
    expect(`${guide.title}${guide.description}`).not.toMatch(/失败|出错/)
  })

  it("未知态优先于其它缺口，且绝不引导用户去重建计划", () => {
    const guide = buildNextStepGuide(
      snapshot({
        hasApiKey: false,
        hasProfileBasics: false,
        hasBodyAnalysis: false,
        planLookup: "unknown",
        hasCheckedIn: false,
      }),
    )

    expect(guide.state).toBe("unknown")
    expect(guide.primaryAction.target).not.toBe("plan")
    expect(guide.primaryAction.label).not.toMatch(/生成/)
  })

  it("资源不存在与请求失败给出不同判定：前者引导生成计划，后者不下结论", () => {
    const missing = buildNextStepGuide(snapshot({ planLookup: "missing" }))
    const failed = buildNextStepGuide(snapshot({ planLookup: "unknown" }))

    expect(missing.currentStep).toBe("plan")
    expect(failed.state).toBe("unknown")
    expect(failed.currentStep).not.toBe(missing.currentStep)
  })
})

describe("buildNextStepGuide 契约", () => {
  const guidingSnapshots: Array<[string, NextStepSnapshot]> = [
    ["key", snapshot({ hasApiKey: false })],
    ["profile", snapshot({ hasProfileBasics: false, hasBodyAnalysis: false, planLookup: "missing" })],
    ["analysis", snapshot({ hasBodyAnalysis: false, planLookup: "missing" })],
    ["plan", snapshot({ planLookup: "missing" })],
    ["first-checkin", snapshot({ hasCheckedIn: false })],
  ]

  it.each(guidingSnapshots)("步骤状态自洽：%s 用例只有当前步为 active，其余按完成度落位", (_label, input) => {
    const guide = buildNextStepGuide(input)
    const statuses = guide.stages.map((stage) => stage.status)
    const activeIndex = statuses.indexOf("active")

    expect(statuses.filter((status) => status === "active")).toHaveLength(1)
    expect(statuses.slice(0, activeIndex)).toEqual(statuses.slice(0, activeIndex).map(() => "completed"))
    expect(statuses.slice(activeIndex + 1)).toEqual(statuses.slice(activeIndex + 1).map(() => "pending"))
  })

  it("同一份快照重复判定结果一致，且不修改输入", () => {
    const input = Object.freeze(snapshot({ hasProfileBasics: false, hasBodyAnalysis: false, planLookup: "missing" }))

    expect(buildNextStepGuide(input)).toEqual(buildNextStepGuide(input))
  })

  it("账本式快照不会因为一次判定被写坏（判定为纯函数）", () => {
    const input: NextStepSnapshot = snapshot({ hasCheckedIn: false })
    const before = { ...input }

    buildNextStepGuide(input)

    expect(input).toEqual(before)
  })

  it("意图到路由的映射覆盖全部取值", () => {
    expect(NEXT_STEP_ROUTES).toEqual({
      profile: "/profile",
      "body-data": "/weight",
      analysis: "/analysis",
      plan: "/plan",
      today: "/",
    })
  })
})

describe("stageStatusFor 页面投影", () => {
  it("按共享 guide 返回指定阶段状态", () => {
    const guide = buildNextStepGuide(snapshot({ planLookup: "missing" }))

    expect(stageStatusFor(guide, "api-key")).toBe("completed")
    expect(stageStatusFor(guide, "plan")).toBe("active")
    expect(stageStatusFor(guide, "first-checkin")).toBe("pending")
  })

  it("日常循环态视为全部完成；未知态不显示进度", () => {
    const daily = buildNextStepGuide(snapshot())
    const unknown = buildNextStepGuide(snapshot({ planLookup: "unknown" }))

    expect(stageStatusFor(daily, "first-checkin")).toBe("completed")
    expect(stageStatusFor(unknown, "plan")).toBe("pending")
  })
})
