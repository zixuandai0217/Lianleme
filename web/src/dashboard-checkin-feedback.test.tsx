// @vitest-environment jsdom
/* 打卡成功后的四段式反馈：本次完成 / 对比 / 恢复建议 / 计划影响。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type {
  BodyAnalysisResult,
  TodayWorkout,
  UserResponse,
  WorkoutFeedback,
  WorkoutRecord,
} from "@/api/types"

const authState = vi.hoisted(() => ({ user: null as UserResponse | null }))
const apiState = vi.hoisted(() => ({
  today: null as TodayWorkout | null,
  record: null as WorkoutRecord | null,
}))

function bodyAnalysis(): BodyAnalysisResult {
  return {
    body_type: "ectomorph",
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
  getTodayWorkout: () => Promise.resolve(apiState.today),
  getCheckinStats: () =>
    Promise.resolve({
      total_checkins: 1,
      streak_days: 1,
      monthly_checkins: 1,
      monthly_completion_rate: 0.6,
      recent_records: [],
    }),
  lookupCurrentPlan: () => Promise.resolve({ lookup: "exists", planId: 7 }),
  completeWorkout: () => Promise.resolve(apiState.record),
}))

import DashboardPage from "@/pages/dashboard"

const trainingDay: TodayWorkout = {
  status: "training_day",
  is_rest_day: false,
  focus: "全身",
  day: 2,
  estimated_duration: 45,
  exercise_count: 1,
  total_sets: 10,
  exercises: [
    {
      name: "深蹲",
      sets: 10,
      reps: "12",
      weight_suggestion: "自重",
      tips: "挺胸收腹",
      rest_seconds: 60,
    },
  ],
}

function checkinRecord(feedback: WorkoutFeedback): WorkoutRecord {
  return {
    id: 1,
    workout_date: "2026-11-02",
    completion_rate: feedback.completion.completion_rate,
    duration_minutes: feedback.completion.duration_minutes,
    ai_feedback: "今天的训练完成了。",
    job_id: feedback.plan_impact.job_id ?? null,
    feedback,
  }
}

const appliedFeedback: WorkoutFeedback = {
  completion: {
    completed_sets: 6,
    total_sets: 10,
    completion_rate: 0.6,
    duration_minutes: 30,
  },
  comparison: {
    has_previous: true,
    previous_completion_rate: 0.8,
    delta_percent: -20,
    direction: "down",
  },
  recovery: {
    source: "model",
    tips: ["补够水，睡够七小时。", "训练后 30 分钟内补充蛋白质。"],
  },
  plan_impact: {
    status: "applied",
    job_id: "job_123",
    direction: "increase",
    reason: "完成率 90%，本次加量 12%",
    before_summary: "难度系数 1.00",
    after_summary: "难度系数 1.12",
  },
}

let root: Root | null
let container: HTMLDivElement

async function renderAndOpenCheckin() {
  authState.user = {
    id: 1,
    openid: "u-1",
    profile: { goal: "减脂", experience: "新手" },
    api_key_status: { has_key: true },
    body_analysis: bodyAnalysis(),
  } as UserResponse
  apiState.today = trainingDay

  await act(async () => {
    root?.render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )
  })
  await act(async () => {})

  const openButton = Array.from(document.querySelectorAll("button")).find((button) =>
    button.textContent?.includes("完成打卡"),
  )
  expect(openButton).toBeTruthy()
  await act(async () => openButton?.click())
}

async function submitCheckin() {
  const submitButton = Array.from(document.querySelectorAll("button")).find((button) =>
    button.textContent?.includes("提交打卡"),
  )
  expect(submitButton).toBeTruthy()
  await act(async () => {
    submitButton?.click()
    await Promise.resolve()
  })
  await act(async () => {})
  return document.body.textContent ?? ""
}

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

describe("打卡后的四段式反馈", () => {
  it("渲染本次完成、与上次对比、恢复建议与已应用的计划影响", async () => {
    apiState.record = checkinRecord(appliedFeedback)
    await renderAndOpenCheckin()

    const text = await submitCheckin()

    expect(text).toContain("本次完成")
    expect(text).toContain("60%")
    expect(text).toContain("6/10 组")
    expect(text).toContain("与上次对比")
    expect(text).toContain("下降了 20 个百分点")
    expect(text).toContain("恢复建议")
    expect(text).toContain("模型生成")
    expect(text).toContain("补够水，睡够七小时。")
    expect(text).toContain("对下周计划的影响")
    expect(text).toContain("加量")
    expect(text).toContain("完成率 90%，本次加量 12%")
    expect(text).toContain("调整前：难度系数 1.00")
    expect(text).toContain("调整后：难度系数 1.12")
  })

  it("待确认时给出「等你确认」文案，另外三段仍然完整", async () => {
    const feedback: WorkoutFeedback = {
      ...appliedFeedback,
      recovery: { source: "fallback", tips: ["补够水，睡够七小时。"] },
      plan_impact: {
        status: "pending_choice",
        job_id: "job_pending",
        direction: null,
        reason: "等你确认风险处理方式后才会生效",
      },
    }
    apiState.record = checkinRecord(feedback)
    await renderAndOpenCheckin()

    const text = await submitCheckin()

    expect(text).toContain("计划调整在等你确认风险处理方式后才会生效")
    expect(text).not.toContain("这次打卡已经影响下周计划")
    expect(text).toContain("本次完成")
    expect(text).toContain("与上次对比")
    expect(text).toContain("恢复建议")
    expect(text).toContain("规则兜底")
  })

  it("作业未投递时计划影响降级，其余三段照常可读", async () => {
    const feedback: WorkoutFeedback = {
      ...appliedFeedback,
      plan_impact: {
        status: "not_dispatched",
        job_id: null,
        direction: null,
        reason: "本次打卡没有投递调整作业，计划保持原样",
      },
    }
    apiState.record = checkinRecord(feedback)
    await renderAndOpenCheckin()

    const text = await submitCheckin()

    expect(text).toContain("这次没有投递调整作业，计划保持原样。")
    expect(text).toContain("本次完成")
    expect(text).toContain("与上次对比")
    expect(text).toContain("恢复建议")
    expect(text).toContain("对下周计划的影响")
  })
})
