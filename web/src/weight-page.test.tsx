// @vitest-environment jsdom
/* 身体数据页的目标体重与目标判定接线：输入回填、完整档案请求体、目标块颜色语义。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { UserResponse, WeightTrend } from "@/api/types"
import type { WeightInsights } from "@/lib/weight-insight"

const authState = vi.hoisted(() => ({ user: null as UserResponse | null }))
const refreshState = vi.hoisted(() => ({ onRefresh: null as (() => void) | null }))
const apiState = vi.hoisted(() => ({
  trend: null as WeightTrend | null,
  insights: null as WeightInsights | null,
  insightCalls: 0,
  updateProfile: null as ((userId: number, data: { profile?: Record<string, unknown> }) => Promise<unknown>) | null,
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    userId: 1,
    user: authState.user,
    refreshUser: () => {
      refreshState.onRefresh?.()
      return Promise.resolve()
    },
  }),
}))

vi.mock("@/api", () => ({
  getWeightTrend: () => Promise.resolve(apiState.trend),
  addWeightRecord: () => Promise.resolve(null),
  deleteWeightRecord: () => Promise.resolve({ message: "ok" }),
  updateProfile: (userId: number, data: { profile?: Record<string, unknown> }) =>
    apiState.updateProfile?.(userId, data) ?? Promise.resolve(authState.user),
}))

vi.mock("@/api/weight-insights", () => ({
  getWeightInsights: () => {
    apiState.insightCalls += 1
    return Promise.resolve(apiState.insights)
  },
}))

import WeightPage from "@/pages/weight"

let root: Root | null
let container: HTMLDivElement

function trendView(partial: Partial<WeightTrend> = {}): WeightTrend {
  return {
    records: [
      { id: 1, weight: 72.4, recorded_date: "2026-02-20" },
      { id: 2, weight: 71.0, recorded_date: "2026-03-17" },
    ],
    total: 2,
    current_weight: 71.0,
    start_weight: 72.4,
    min_weight: 71.0,
    max_weight: 72.4,
    change: -1.4,
    ...partial,
  }
}

function insightsView(
  goal: WeightInsights["goal"],
  d30: { change: number; direction: "down" | "up" | "flat" } = { change: -1.4, direction: "down" },
): WeightInsights {
  const window = {
    days: 30,
    start_date: "2026-02-16",
    end_date: "2026-03-17",
    sample_count: 4,
    change: d30.change,
    direction: d30.direction,
    min: { weight: 71.0, recorded_date: "2026-03-17" },
    max: { weight: 72.4, recorded_date: "2026-02-20" },
    insufficient: false,
  }
  return {
    anchor_date: "2026-03-17",
    is_stale: false,
    stale_days: 0,
    windows: { d7: { ...window, days: 7, change: -0.4 }, d30: window },
    weekly: [],
    training_data_available: false,
    goal,
  }
}

/** 挂载身体数据页并等一次数据回填。 */
async function renderWeightPage(options: {
  profile?: UserResponse["profile"]
  goal: WeightInsights["goal"]
  d30?: { change: number; direction: "down" | "up" | "flat" }
}) {
  authState.user = { id: 1, openid: "u-1", profile: options.profile } as UserResponse
  apiState.trend = trendView()
  apiState.insights = insightsView(options.goal, options.d30)

  await act(async () => {
    root?.render(<WeightPage />)
  })
  await act(async () => {})
}

const targetWeightInput = () =>
  container.querySelector<HTMLInputElement>("#p-target-weight")

const goalBlock = () => container.querySelector<HTMLElement>('[data-testid="weight-goal"]')

const clickButton = async (label: string) => {
  const button = Array.from(container.querySelectorAll("button")).find(
    (item) => item.textContent?.trim().includes(label),
  )
  if (!button) throw new Error(`button not found: ${label}`)
  await act(async () => {
    button.click()
  })
  await act(async () => {})
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  apiState.updateProfile = null
  apiState.insightCalls = 0
  refreshState.onRefresh = null
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
})

describe("身体数据页：目标体重与目标判定", () => {
  it("renders the optional target weight input prefilled from the profile", async () => {
    await renderWeightPage({
      profile: { height: 170, age: 25, gender: "男", goal: "减脂", experience: "初级", target_weight: 68 },
      goal: { mode: "none", verdict: "neutral", reason: "no_goal" },
    })

    expect(container.textContent).toContain("目标体重 (kg)")
    expect(container.textContent).toContain("保留 1 位小数")
    expect(targetWeightInput()).not.toBeNull()
    expect(targetWeightInput()?.value).toBe("68.0")
  })

  it("submits the whole profile including target weight", async () => {
    const calls: { userId: number; data: { profile?: Record<string, unknown> } }[] = []
    apiState.updateProfile = (userId, data) => {
      calls.push({ userId, data })
      return Promise.resolve(authState.user)
    }

    await renderWeightPage({
      profile: {
        height: 170,
        age: 25,
        gender: "男",
        goal: "减脂",
        experience: "初级",
        weight: 72,
        target_weight: 68,
      },
      goal: { mode: "none", verdict: "neutral", reason: "no_goal" },
    })

    await clickButton("保存档案")

    expect(calls).toHaveLength(1)
    expect(calls[0].userId).toBe(1)
    expect(calls[0].data.profile).toMatchObject({
      height: 170,
      age: 25,
      gender: "男",
      goal: "减脂",
      experience: "初级",
      weight: 72,
      target_weight: 68,
    })
  })

  it("reads the saved profile back and keeps every field on the next save", async () => {
    const savedProfile = {
      height: 170,
      age: 25,
      gender: "男",
      goal: "减脂",
      experience: "初级",
      weight: 71,
      target_weight: 66,
      body_fat: 18,
    }
    const calls: { data: { profile?: Record<string, unknown> } }[] = []
    apiState.updateProfile = (_userId, data) => {
      calls.push({ data })
      return Promise.resolve({ id: 1, openid: "u-1", profile: savedProfile })
    }
    refreshState.onRefresh = () => {
      authState.user = { id: 1, openid: "u-1", profile: savedProfile } as UserResponse
    }

    await renderWeightPage({
      profile: { height: 170, age: 25, gender: "男", goal: "减脂", experience: "初级", weight: 71, target_weight: 68 },
      goal: { mode: "none", verdict: "neutral", reason: "no_goal" },
    })

    await clickButton("保存档案")
    // 保存成功后按钮文案会变成「已保存 ✓」，复用同一个元素再存一次
    const saveAgain = Array.from(container.querySelectorAll("button")).find((item) =>
      (item.textContent ?? "").includes("保存"),
    )!
    await act(async () => {
      saveAgain.click()
    })
    await act(async () => {})

    // 第二次保存的基线来自保存后重新读取的档案：表单未负责的字段同样不能丢
    expect(calls).toHaveLength(2)
    expect(calls[1].data.profile).toMatchObject({
      height: 170,
      age: 25,
      gender: "男",
      goal: "减脂",
      experience: "初级",
      weight: 71,
      target_weight: 68,
      body_fat: 18,
    })
  })

  it("omits target weight instead of sending null when it is left empty", async () => {
    const calls: { data: { profile?: Record<string, unknown> } }[] = []
    apiState.updateProfile = (_userId, data) => {
      calls.push({ data })
      return Promise.resolve(authState.user)
    }

    await renderWeightPage({
      profile: { height: 170, age: 25, gender: "男", goal: "减脂", experience: "初级", weight: 72 },
      goal: { mode: "none", verdict: "neutral", reason: "no_goal" },
    })

    await clickButton("保存档案")

    expect(calls).toHaveLength(1)
    expect(calls[0].data.profile?.target_weight).toBeUndefined()
    expect(calls[0].data.profile?.target_weight).not.toBeNull()
  })

  it("refuses an out-of-range target weight instead of silently clearing it", async () => {
    const calls: unknown[] = []
    apiState.updateProfile = (_userId, data) => {
      calls.push(data)
      return Promise.resolve(authState.user)
    }

    await renderWeightPage({
      profile: { weight: 72, target_weight: 68 },
      goal: { mode: "none", verdict: "neutral", reason: "no_goal" },
    })

    const input = targetWeightInput()
    expect(input).not.toBeNull()
    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!
      setValue.call(input, "0")
      input!.dispatchEvent(new Event("input", { bubbles: true }))
    })

    await clickButton("保存档案")

    // 非法值必须拦在请求之前：静默置 undefined 会在整体替换时清掉已存的目标体重
    expect(calls).toHaveLength(0)
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("目标体重")
  })

  it("colors the goal block positive when the verdict is on track", async () => {
    await renderWeightPage({
      profile: { goal: "减脂", target_weight: 68 },
      goal: { mode: "numeric", verdict: "on_track", reason: "change_matches_target", gap: 3, target_weight: 68, expected_direction: "down" },
    })

    expect(goalBlock()?.dataset.tone).toBe("positive")
    expect(goalBlock()?.textContent).toContain("朝目标前进")
    expect(goalBlock()?.className).toContain("text-brand-green")
  })

  it("colors the goal block as a warning when the verdict is off track", async () => {
    await renderWeightPage({
      profile: { goal: "减脂", target_weight: 68 },
      goal: { mode: "numeric", verdict: "off_track", reason: "change_against_target", gap: 3, target_weight: 68, expected_direction: "down" },
    })

    expect(goalBlock()?.dataset.tone).toBe("warning")
    expect(goalBlock()?.textContent).toContain("偏离目标")
    expect(goalBlock()?.className).toContain("text-destructive")
  })

  it("renders no goal block at all without a goal", async () => {
    await renderWeightPage({
      profile: { goal: undefined },
      goal: { mode: "none", verdict: "neutral", reason: "no_goal" },
    })

    expect(goalBlock()).toBeNull()
    expect(container.textContent).toContain("趋势解读")
  })

  it("never warns a 增肌 user for a rising weight", async () => {
    await renderWeightPage({
      profile: { goal: "增肌" },
      goal: {
        mode: "direction",
        verdict: "on_track",
        reason: "change_matches_goal_direction",
        goal_label: "增肌",
        expected_direction: "up",
      },
      d30: { change: 1.2, direction: "up" },
    })

    expect(goalBlock()?.dataset.tone).toBe("positive")
    expect(goalBlock()?.textContent).toContain("（按目标方向推断）")
    expect(goalBlock()?.textContent).toContain("增肌期望上升")
    expect(goalBlock()?.className).not.toContain("text-destructive")
  })

  it("keeps the whole insight neutral-toned when no goal is configured", async () => {
    await renderWeightPage({
      profile: { height: 170 },
      goal: { mode: "none", verdict: "neutral", reason: "no_goal" },
      d30: { change: 1.4, direction: "up" },
    })

    expect(container.querySelectorAll("[data-tone]")).toHaveLength(0)
    expect(container.textContent).toContain("最近 30 天")
  })

  it("recomputes the insight right after the profile is saved", async () => {
    await renderWeightPage({
      profile: { height: 170, goal: "减脂" },
      goal: {
        mode: "direction",
        verdict: "on_track",
        reason: "change_matches_goal_direction",
        goal_label: "减脂",
        expected_direction: "down",
      },
    })

    expect(apiState.insightCalls).toBe(1)

    await clickButton("保存档案")

    // 目标判定口径来自档案：保存后必须重新取数，否则用户刚设完目标看到的是旧结论
    expect(apiState.insightCalls).toBe(2)
  })
})
