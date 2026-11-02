// @vitest-environment jsdom
/* 分析页四阶段闭环：阶段状态与主行动都投影共享引导，而不是另写一套判定。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { PlanResponse, UserResponse } from "@/api/types"

const authState = vi.hoisted(() => ({ user: null as UserResponse | null }))
const refreshUser = vi.hoisted(() => vi.fn(async () => undefined))
const api = vi.hoisted(() => ({
  startAnalyze: vi.fn(),
  getAnalyzeResult: vi.fn(),
  getAnalysisHistory: vi.fn(),
  lookupCurrentPlan: vi.fn(),
  getCheckinStats: vi.fn(),
  generatePlan: vi.fn(),
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ userId: 1, user: authState.user, refreshUser }),
}))
vi.mock("@/api", () => api)

import AnalysisPage from "@/pages/analysis"

let root: Root | null
let container: HTMLDivElement

const bodyAnalysis = {
  body_type: "mesomorph",
  body_fat_range: "18-22%",
  weak_muscles: ["背"],
  strengths: ["腿"],
  muscle_scores: {},
  summary: "保持训练",
}

const readyProfile = { goal: "减脂", experience: "新手" }

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

function LocationResult({ label }: { label: string }) {
  const location = useLocation()
  return <output data-route={label} data-path={location.pathname}>{label}</output>
}

const findButton = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes(label),
  )

const stageStatus = (key: string) =>
  container.querySelector(`[data-stage-key="${key}"]`)?.getAttribute("data-status")

async function flush() {
  await act(async () => {})
  await act(async () => {})
}

async function renderAnalysis() {
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={["/analysis"]}>
        <Routes>
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/plan" element={<LocationResult label="plan" />} />
          <Route path="/profile" element={<LocationResult label="profile" />} />
          <Route path="/weight" element={<LocationResult label="weight" />} />
          <Route path="/" element={<LocationResult label="home" />} />
        </Routes>
      </MemoryRouter>,
    )
  })
  await flush()
  return container.textContent ?? ""
}

function stats(total = 0) {
  return {
    total_checkins: total,
    streak_days: 0,
    monthly_checkins: 0,
    monthly_completion_rate: 0,
    recent_records: [],
  }
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  authState.user = {
    id: 1,
    openid: "u-1",
    api_key_status: { has_key: true },
    profile: readyProfile,
    body_analysis: bodyAnalysis,
  } as UserResponse
  api.getAnalysisHistory.mockResolvedValue({ records: [], total: 0 })
  api.getCheckinStats.mockResolvedValue(stats(0))
  api.lookupCurrentPlan.mockResolvedValue({ lookup: "missing" })
  api.generatePlan.mockResolvedValue(planResponse())
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

describe("分析页阶段状态", () => {
  it("分析完成但无计划时：分析阶段 completed、计划阶段 active，主行动为生成专属训练计划", async () => {
    const text = await renderAnalysis()

    expect(stageStatus("upload")).toBe("completed")
    expect(stageStatus("analyze")).toBe("completed")
    expect(stageStatus("plan")).toBe("active")
    expect(stageStatus("train")).toBe("pending")
    expect(text).toContain("生成专属训练计划")
    expect(container.querySelector('[data-next-step="plan"]')).not.toBeNull()

    const generate = findButton("生成专属训练计划")
    expect(generate).toBeDefined()
    await act(async () => {
      generate?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await flush()

    expect(api.generatePlan).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain("查看训练计划")
  })

  it("已有计划时：计划阶段 completed、训练阶段 active，主行动切换为查看训练计划并跳转计划页", async () => {
    api.lookupCurrentPlan.mockResolvedValue({ lookup: "exists", planId: 7 })

    const text = await renderAnalysis()

    expect(stageStatus("upload")).toBe("completed")
    expect(stageStatus("analyze")).toBe("completed")
    expect(stageStatus("plan")).toBe("completed")
    expect(stageStatus("train")).toBe("active")
    expect(text).toContain("查看训练计划")
    expect(text).not.toContain("生成专属训练计划")
    expect(container.querySelector('[data-next-step="first-checkin"]')).not.toBeNull()

    const viewPlan = findButton("查看训练计划")
    await act(async () => {
      viewPlan?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    expect(container.querySelector('[data-route="plan"]')?.getAttribute("data-path")).toBe("/plan")
  })

  it("缺 Key 时四阶段不显示虚假进度，主行动配置 Key", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: false },
      profile: readyProfile,
      body_analysis: bodyAnalysis,
    } as UserResponse

    const text = await renderAnalysis()

    expect(stageStatus("upload")).toBe("pending")
    expect(stageStatus("analyze")).toBe("pending")
    expect(stageStatus("plan")).toBe("pending")
    expect(stageStatus("train")).toBe("pending")
    expect(text).toContain("先配置自己的 AI Key")
    expect(findButton("配置 API Key")).toBeDefined()
  })
})
