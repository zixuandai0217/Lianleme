// @vitest-environment jsdom
/* 首页引导的用户可见行为：单一主行动、各缺口指向正确页面、未知态不误导、日常态不打扰。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { BodyAnalysisResult, PlanLookup, UserResponse } from "@/api/types"

const authState = vi.hoisted(() => ({ user: null as UserResponse | null }))
const planState = vi.hoisted(() => ({
  lookup: "unknown" as PlanLookup,
  planId: undefined as number | undefined,
}))
const checkinState = vi.hoisted(() => ({ total: 0 }))

/** 首页只读体型分类，但类型要求完整结果；给齐字段避免测试靠类型断言作弊。 */
function bodyAnalysis(bodyType: string): BodyAnalysisResult {
  return {
    body_type: bodyType,
    body_fat_range: "18-22%",
    weak_muscles: [],
    strengths: [],
    muscle_scores: {},
    summary: "",
  }
}

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ userId: 1, user: authState.user }),
}))

vi.mock("@/api", () => ({
  getTodayWorkout: () => Promise.resolve(null),
  getCheckinStats: () =>
    Promise.resolve({
      total_checkins: checkinState.total,
      streak_days: 0,
      monthly_checkins: 0,
      monthly_completion_rate: 0,
      recent_records: [],
    }),
  lookupCurrentPlan: () =>
    Promise.resolve({ lookup: planState.lookup, planId: planState.planId }),
  completeWorkout: () => Promise.reject(new Error("check-in is not part of this test")),
}))

import DashboardPage from "@/pages/dashboard"

let root: Root | null
let container: HTMLDivElement

interface RenderOptions {
  user: Partial<UserResponse>
  lookup: PlanLookup
  planId?: number
  totalCheckins?: number
}

/** 挂载首页并等一次数据回填，返回整页可读文本。 */
async function renderDashboard({ user, lookup, planId, totalCheckins = 0 }: RenderOptions) {
  authState.user = { id: 1, openid: "u-1", ...user } as UserResponse
  planState.lookup = lookup
  planState.planId = planId
  checkinState.total = totalCheckins

  await act(async () => {
    root?.render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )
  })
  await act(async () => {})

  return container.textContent ?? ""
}

const buttonLabels = () =>
  Array.from(container.querySelectorAll("button")).map((button) => button.textContent?.trim() ?? "")

const countButtons = (fragment: string) =>
  buttonLabels().filter((label) => label.includes(fragment)).length

const readyProfile = { goal: "减脂", experience: "新手" }

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
})

describe("首页首用引导", () => {
  it("没有 AI Key 时引导配置 Key，且不提供会生成计划的入口", async () => {
    const text = await renderDashboard({
      user: { profile: readyProfile, api_key_status: { has_key: false }, body_analysis: bodyAnalysis("ectomorph") },
      lookup: "missing",
    })

    expect(text).toContain("先配置自己的 AI Key")
    expect(countButtons("配置 API Key")).toBe(1)
    expect(countButtons("生成训练计划")).toBe(0)
  })

  it("缺身体档案时引导去填写档案，而不是先做分析", async () => {
    const text = await renderDashboard({
      user: { profile: {}, api_key_status: { has_key: true } },
      lookup: "missing",
    })

    expect(text).toContain("补全身体档案")
    expect(countButtons("填写身体档案")).toBe(1)
    expect(text).not.toContain("先配置自己的 AI Key")
  })

  it("计划查询返回 404 时引导生成计划，并展示首次使用进度", async () => {
    const text = await renderDashboard({
      user: { profile: readyProfile, api_key_status: { has_key: true }, body_analysis: bodyAnalysis("mesomorph") },
      lookup: "missing",
    })

    expect(text).toContain("生成本周训练计划")
    expect(text).toContain("首次使用进度")
    expect(countButtons("生成训练计划")).toBe(1)
  })

  it("计划查询失败时进入中性未知态，不显示进度也不引导重建计划", async () => {
    const text = await renderDashboard({
      user: { profile: readyProfile, api_key_status: { has_key: true }, body_analysis: bodyAnalysis("endomorph") },
      lookup: "unknown",
    })

    expect(text).toContain("先看看今天的安排")
    expect(text).not.toContain("首次使用进度")
    expect(countButtons("生成训练计划")).toBe(0)
    expect(text).not.toMatch(/失败|出错/)
  })

  it("全部就绪时回到日常训练态，不再出现引导进度", async () => {
    const text = await renderDashboard({
      user: { profile: readyProfile, api_key_status: { has_key: true }, body_analysis: bodyAnalysis("ectomorph") },
      lookup: "exists",
      planId: 7,
      totalCheckins: 3,
    })

    expect(text).not.toContain("首次使用进度")
    expect(countButtons("生成训练计划")).toBe(0)
    expect(text).not.toContain("先配置自己的 AI Key")
  })
})
