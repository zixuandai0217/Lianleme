// @vitest-environment jsdom
/* AC1：同一份首用快照驱动首页、计划页空态、分析页，三处必须给同一个「当前步」。 */
import { act, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { PlanLookup, PlanResponse, UserResponse } from "@/api/types"

const authState = vi.hoisted(() => ({ user: null as UserResponse | null }))
const lookupState = vi.hoisted(() => ({
  lookup: "missing" as PlanLookup,
  planId: undefined as number | undefined,
  totalCheckins: 0,
}))
const api = vi.hoisted(() => ({
  getTodayWorkout: vi.fn(),
  getCheckinStats: vi.fn(),
  lookupCurrentPlan: vi.fn(),
  completeWorkout: vi.fn(),
  getCurrentPlan: vi.fn(),
  generatePlan: vi.fn(),
  startAnalyze: vi.fn(),
  getAnalyzeResult: vi.fn(),
  getAnalysisHistory: vi.fn(),
}))
const refreshUser = vi.hoisted(() => vi.fn(async () => undefined))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ userId: 1, user: authState.user, refreshUser }),
}))
vi.mock("@/api", () => api)

import DashboardPage from "@/pages/dashboard"
import PlanPage from "@/pages/plan"
import AnalysisPage from "@/pages/analysis"

let root: Root | null
let container: HTMLDivElement

const bodyAnalysis = {
  body_type: "mesomorph",
  body_fat_range: "18-22%",
  weak_muscles: [],
  strengths: [],
  muscle_scores: {},
  summary: "",
}

const readyProfile = { goal: "减脂", experience: "新手" }
const keyReady = { has_key: true }

const planResponse = (): PlanResponse => ({
  message: "获取成功",
  plan: {
    id: 7,
    user_id: 1,
    week_start: "2026-03-16",
    difficulty_factor: 1,
    status: "active",
    weekly_plan: [],
  },
})

function stats(total: number) {
  return {
    total_checkins: total,
    streak_days: 0,
    monthly_checkins: total,
    monthly_completion_rate: 0,
    recent_records: [],
  }
}

async function renderPage(page: ReactNode): Promise<string> {
  await act(async () => {
    root?.render(<MemoryRouter>{page}</MemoryRouter>)
  })
  await act(async () => {})
  await act(async () => {})
  return container.textContent ?? ""
}

interface Case {
  name: string
  user: UserResponse
  lookup: PlanLookup
  checkins: number
  expectedStep: string | null
  expectedTitle: string | null
}

const cases: Case[] = [
  {
    name: "缺 Key",
    user: { id: 1, openid: "u-1", api_key_status: { has_key: false }, profile: readyProfile, body_analysis: bodyAnalysis },
    lookup: "missing",
    checkins: 0,
    expectedStep: "api-key",
    expectedTitle: "先配置自己的 AI Key",
  },
  {
    name: "缺档案",
    user: { id: 1, openid: "u-1", api_key_status: keyReady, profile: { goal: "减脂" } },
    lookup: "missing",
    checkins: 0,
    expectedStep: "profile",
    expectedTitle: "补全身体档案",
  },
  {
    name: "缺分析",
    user: { id: 1, openid: "u-1", api_key_status: keyReady, profile: readyProfile },
    lookup: "missing",
    checkins: 0,
    expectedStep: "analysis",
    expectedTitle: "完成一次体型分析",
  },
  {
    name: "缺计划",
    user: { id: 1, openid: "u-1", api_key_status: keyReady, profile: readyProfile, body_analysis: bodyAnalysis },
    lookup: "missing",
    checkins: 0,
    expectedStep: "plan",
    expectedTitle: "生成本周训练计划",
  },
  {
    name: "缺打卡",
    user: { id: 1, openid: "u-1", api_key_status: keyReady, profile: readyProfile, body_analysis: bodyAnalysis },
    lookup: "exists",
    checkins: 0,
    expectedStep: "first-checkin",
    expectedTitle: "完成第一次训练打卡",
  },
  {
    name: "已完成",
    user: { id: 1, openid: "u-1", api_key_status: keyReady, profile: readyProfile, body_analysis: bodyAnalysis },
    lookup: "exists",
    checkins: 3,
    expectedStep: null,
    expectedTitle: null,
  },
]

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

  api.lookupCurrentPlan.mockImplementation(() =>
    Promise.resolve({ lookup: lookupState.lookup, planId: lookupState.planId }),
  )
  api.getCheckinStats.mockImplementation(() => Promise.resolve(stats(lookupState.totalCheckins)))
  api.getCurrentPlan.mockImplementation(() =>
    lookupState.lookup === "exists"
      ? Promise.resolve(planResponse())
      : Promise.reject(new Error("暂无训练计划")),
  )
  api.getTodayWorkout.mockResolvedValue(null)
  api.completeWorkout.mockRejectedValue(new Error("not part of this test"))
  api.generatePlan.mockRejectedValue(new Error("not part of this test"))
  api.startAnalyze.mockRejectedValue(new Error("not part of this test"))
  api.getAnalyzeResult.mockRejectedValue(new Error("not part of this test"))
  api.getAnalysisHistory.mockResolvedValue({ records: [], total: 0 })

  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  vi.clearAllMocks()
})

describe("首用当前步跨页一致", () => {
  it.each(cases)("$name：首页、计划页、分析页显示同一个当前步", async (testCase) => {
    authState.user = testCase.user
    lookupState.lookup = testCase.lookup
    lookupState.planId = testCase.lookup === "exists" ? 7 : undefined
    lookupState.totalCheckins = testCase.checkins

    const homeText = await renderPage(<DashboardPage />)

    const planText = await renderPage(<PlanPage />)
    const planStep =
      container.querySelector("[data-next-step]")?.getAttribute("data-next-step") ?? null

    const analysisText = await renderPage(<AnalysisPage />)
    const analysisStep =
      container.querySelector("[data-next-step]")?.getAttribute("data-next-step") ?? null

    if (testCase.expectedTitle) {
      expect(homeText).toContain(testCase.expectedTitle)
      expect(planText).toContain(testCase.expectedTitle)
      expect(analysisText).toContain(testCase.expectedTitle)
      expect(planStep).toBe(testCase.expectedStep)
      expect(analysisStep).toBe(testCase.expectedStep)
      return
    }

    // 全部完成：三处都不再出现「当前步」，首页不再显示首次使用进度。
    expect(homeText).not.toContain("首次使用进度")
    expect(planStep).toBeNull()
    expect(analysisStep).toBeNull()
    expect(analysisText).toContain("查看训练计划")
  })
})
