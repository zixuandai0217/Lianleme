// @vitest-environment jsdom
/* 今日三态在首页的用户可见差异：无计划不能长得像休息日。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { BodyAnalysisResult, TodayWorkout, UserResponse } from "@/api/types"

const authState = vi.hoisted(() => ({ user: null as UserResponse | null }))
const todayState = vi.hoisted(() => ({ workout: null as TodayWorkout | null }))

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
  getTodayWorkout: () => Promise.resolve(todayState.workout),
  getCheckinStats: () =>
    Promise.resolve({
      total_checkins: 3,
      streak_days: 1,
      monthly_checkins: 3,
      monthly_completion_rate: 0.9,
      recent_records: [],
    }),
  lookupCurrentPlan: () => Promise.resolve({ lookup: "exists", planId: 7 }),
  completeWorkout: () => Promise.reject(new Error("check-in is not part of this test")),
}))

import DashboardPage from "@/pages/dashboard"

let root: Root | null
let container: HTMLDivElement

async function renderDashboard(today: TodayWorkout | null, initialEntry = "/") {
  authState.user = {
    id: 1,
    openid: "u-1",
    profile: { goal: "减脂", experience: "新手" },
    api_key_status: { has_key: true },
    body_analysis: bodyAnalysis("ectomorph"),
  } as UserResponse
  todayState.workout = today

  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <DashboardPage />
      </MemoryRouter>,
    )
  })
  await act(async () => {})

  return container.textContent ?? ""
}

const buttonLabels = () =>
  Array.from(container.querySelectorAll("button")).map((button) => button.textContent?.trim() ?? "")

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

const restDay: TodayWorkout = {
  status: "rest_day",
  is_rest_day: true,
  message: "今日休息，好好恢复",
}

const noPlan: TodayWorkout = { status: "no_plan", is_rest_day: false }

const trainingDay: TodayWorkout = {
  status: "training_day",
  is_rest_day: false,
  focus: "全身",
  day: 2,
  estimated_duration: 45,
  exercise_count: 1,
  total_sets: 3,
  exercises: [
    {
      name: "深蹲",
      sets: 3,
      reps: "12",
      weight_suggestion: "自重",
      tips: "挺胸收腹",
      rest_seconds: 60,
    },
  ],
}

describe("首页今日三态", () => {
  it("休息日给出恢复文案与恢复入口", async () => {
    const text = await renderDashboard(restDay)

    expect(text).toContain("今天留给恢复")
    expect(text).toContain("今日休息，好好恢复")
    expect(buttonLabels().some((label) => label.includes("咨询恢复建议"))).toBe(true)
    expect(text).not.toContain("还没有本周训练计划")
  })

  it("无计划给出「去生成计划」的分支，而不是伪装成休息日", async () => {
    const text = await renderDashboard(noPlan)

    expect(text).toContain("还没有本周训练计划")
    expect(buttonLabels().some((label) => label.includes("去生成本周计划"))).toBe(true)
    expect(text).not.toContain("今天留给恢复")
    expect(buttonLabels().some((label) => label.includes("咨询恢复建议"))).toBe(false)
  })

  it("两种空态的用户可见文案彼此不同", async () => {
    const restText = await renderDashboard(restDay)

    // 同一 userId 下重新渲染不会重新取数，必须真正重挂载才能看到另一态的文案。
    await act(async () => root?.unmount())
    root = null
    container.remove()
    container = document.createElement("div")
    document.body.append(container)
    root = createRoot(container)

    const noPlanText = await renderDashboard(noPlan)

    expect(restText).not.toBe(noPlanText)
    expect(restText.includes("今天留给恢复")).toBe(true)
    expect(noPlanText.includes("今天留给恢复")).toBe(false)
  })

  it("训练日照常展示动作清单与打卡入口", async () => {
    const text = await renderDashboard(trainingDay)

    expect(text).toContain("深蹲")
    expect(text).toContain("全身")
    expect(text).toContain("45 分钟")
    expect(buttonLabels().some((label) => label.includes("完成打卡"))).toBe(true)
  })

  it("带 ?checkin=1 进入时直接打开打卡弹窗（会话页收尾入口）", async () => {
    await renderDashboard(trainingDay, "/?checkin=1")

    // 弹窗渲染在 portal 里，必须查整个 document。
    expect(document.body.textContent).toContain("训练打卡")
    expect(document.body.textContent).toContain("完成组数")
  })
})
