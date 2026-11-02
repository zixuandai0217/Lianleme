// @vitest-environment jsdom
/* 计划页空态：投影共享引导、中性降级、档案/Key 入口与单一主行动。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { PlanResponse, UserResponse } from "@/api/types"

const authState = vi.hoisted(() => ({ user: null as UserResponse | null }))
const api = vi.hoisted(() => ({
  getCurrentPlan: vi.fn(),
  lookupCurrentPlan: vi.fn(),
  getCheckinStats: vi.fn(),
  generatePlan: vi.fn(),
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ userId: 1, user: authState.user }),
}))
vi.mock("@/api", () => api)

import PlanPage from "@/pages/plan"

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

function planResponse(): PlanResponse {
  return {
    message: "获取成功",
    plan: {
      id: 1,
      user_id: 1,
      week_start: "2026-03-16",
      difficulty_factor: 1,
      status: "active",
      weekly_plan: [
        {
          day: 1,
          focus: "push",
          estimated_duration: 40,
          is_rest_day: false,
          exercises: [],
        },
      ],
    },
  }
}

function LocationResult({ label }: { label: string }) {
  const location = useLocation()
  return <output data-route={label} data-path={location.pathname}>{label}</output>
}

const findButton = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes(label),
  )

async function flush() {
  await act(async () => {})
  await act(async () => {})
}

async function renderPlan() {
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={["/plan"]}>
        <Routes>
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/weight" element={<LocationResult label="weight" />} />
          <Route path="/analysis" element={<LocationResult label="analysis" />} />
          <Route path="/profile" element={<LocationResult label="profile" />} />
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
  api.getCheckinStats.mockResolvedValue(stats(0))
  api.lookupCurrentPlan.mockResolvedValue({ lookup: "missing" })
  api.generatePlan.mockRejectedValue(new Error("not part of this test"))
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

describe("计划页空态", () => {
  it("没有计划时渲染中性空态，不出现红色错误告警条", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: true },
      profile: readyProfile,
      body_analysis: bodyAnalysis,
    } as UserResponse
    api.getCurrentPlan.mockRejectedValue(new Error("暂无训练计划，请先完成体型分析"))

    const text = await renderPlan()

    expect(text).toContain("生成本周训练计划")
    expect(text).toContain("首次使用进度")
    expect(container.querySelector('[role="alert"]')).toBeNull()
    expect(text).not.toContain("生成一周训练")
    expect(container.querySelector('[data-next-step="plan"]')).not.toBeNull()
  })

  it("计划查询非 404 失败时降级为中性提示，不引导生成计划", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: true },
      profile: readyProfile,
      body_analysis: bodyAnalysis,
    } as UserResponse
    api.getCurrentPlan.mockRejectedValue(new Error("网络错误"))
    api.lookupCurrentPlan.mockResolvedValue({ lookup: "unknown" })

    const text = await renderPlan()

    expect(text).toContain("先看看今天的安排")
    expect(container.querySelector('[role="alert"]')).toBeNull()
    expect(findButton("生成训练计划")).toBeUndefined()
    expect(findButton("查看今日安排")).toBeDefined()
    expect(container.querySelector('[data-next-step="none"]')).not.toBeNull()
  })

  it("当前步由共享判定决定：缺分析时不会把生成计划写成当前步", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: true },
      profile: readyProfile,
    } as UserResponse
    api.getCurrentPlan.mockRejectedValue(new Error("暂无训练计划"))

    const text = await renderPlan()

    expect(container.querySelector('[data-next-step="analysis"]')).not.toBeNull()
    expect(text).toContain("完成一次体型分析")
    expect(text).not.toContain("生成一周训练")
    expect(findButton("生成训练计划")).toBeUndefined()
    expect(findButton("去做体型分析")).toBeDefined()
  })

  it("已配 Key 但缺档案时唯一主行动指向身体数据页", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: true },
      profile: { goal: "减脂" },
    } as UserResponse
    api.getCurrentPlan.mockRejectedValue(new Error("暂无训练计划"))

    await renderPlan()

    expect(container.querySelectorAll("button")).toHaveLength(1)
    const button = findButton("填写身体档案")
    expect(button).toBeDefined()

    await act(async () => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    expect(container.querySelector('[data-route="weight"]')?.getAttribute("data-path")).toBe("/weight")
  })

  it("未配 Key 时唯一主行动改为配置 API Key", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: false },
      profile: readyProfile,
      body_analysis: bodyAnalysis,
    } as UserResponse
    api.getCurrentPlan.mockRejectedValue(new Error("暂无训练计划"))

    const text = await renderPlan()

    expect(container.querySelectorAll("button")).toHaveLength(1)
    expect(findButton("配置 API Key")).toBeDefined()
    expect(findButton("填写身体档案")).toBeUndefined()
    expect(findButton("生成训练计划")).toBeUndefined()
    expect(text).toContain("先配置自己的 AI Key")
  })
})

describe("计划页已有计划时的下一步", () => {
  it("有计划但未打卡时，计划页当前步与共享判定一致（第一次打卡）", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: true },
      profile: readyProfile,
      body_analysis: bodyAnalysis,
    } as UserResponse
    api.getCurrentPlan.mockResolvedValue(planResponse())
    api.getCheckinStats.mockResolvedValue(stats(0))

    const text = await renderPlan()

    expect(text).toContain("完成第一次训练打卡")
    expect(text).not.toContain("生成一周训练")
    expect(container.querySelector('[data-next-step="first-checkin"]')).not.toBeNull()
  })

  it("已打卡时计划页不再显示下一步状态条", async () => {
    authState.user = {
      id: 1,
      openid: "u-1",
      api_key_status: { has_key: true },
      profile: readyProfile,
      body_analysis: bodyAnalysis,
    } as UserResponse
    api.getCurrentPlan.mockResolvedValue(planResponse())
    api.getCheckinStats.mockResolvedValue(stats(2))

    await renderPlan()

    expect(container.querySelector("[data-next-step]")).toBeNull()
  })
})
