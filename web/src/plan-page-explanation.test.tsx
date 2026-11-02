// @vitest-environment jsdom
/* 计划页解释卡：默认收起、展开后四块可见、三档降级文案与目标优先级。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { PlanExplanation, PlanResponse, UserResponse } from "@/api/types"

const state = vi.hoisted(() => ({
  response: null as PlanResponse | null,
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    userId: 1,
    user: {
      id: 1,
      openid: "u-1",
      profile: { goal: "减脂", experience: "新手" },
      body_analysis: {
        body_type: "mesomorph",
        body_fat_range: "18-22%",
        weak_muscles: [],
        strengths: [],
        muscle_scores: {},
        summary: "",
      },
    } as UserResponse,
  }),
}))

vi.mock("@/api", () => ({
  getCurrentPlan: () => Promise.resolve(state.response),
  generatePlan: () => Promise.reject(new Error("not part of this test")),
}))

import PlanPage from "@/pages/plan"

let root: Root | null
let container: HTMLDivElement

function planResponse(explanation: PlanExplanation | null | undefined): PlanResponse {
  return {
    message: "获取成功",
    plan: {
      id: 1,
      user_id: 1,
      week_start: "2026-03-16",
      difficulty_factor: 1.35,
      status: "active",
      weekly_plan: [
        {
          day: 1,
          focus: "push",
          estimated_duration: 40,
          is_rest_day: false,
          exercises: [
            { name: "卧推", sets: 3, reps: "8-12", weight_suggestion: "40%", tips: "肩胛收紧", rest_seconds: 90 },
            { name: "肩推", sets: 2, reps: "10", weight_suggestion: "轻", tips: "", rest_seconds: 60 },
          ],
        },
        {
          day: 2,
          focus: "恢复",
          estimated_duration: 0,
          is_rest_day: true,
          exercises: [],
        },
      ],
    },
    explanation,
  }
}

const explanationWithAdjustment = (direction: "increase" | "keep"): PlanExplanation => ({
  generation: {
    body_type: "mesomorph",
    body_fat_range: "18-22%",
    weak_muscles: ["背部"],
    strengths: ["腿部"],
    analysis_summary: "下肢占优",
    captured_at: "2026-03-15T08:00:00Z",
    profile_goal: "增肌",
  },
  latest_adjustment: {
    direction,
    trigger: "completion_rate",
    completion_rate: 0.85,
    occurred_at: "2026-03-16T05:00:00Z",
    reason: "完成率 85%，表现优秀",
  },
})

async function renderPlan(response: PlanResponse) {
  state.response = response
  await act(async () => {
    root?.render(
      <MemoryRouter>
        <PlanPage />
      </MemoryRouter>,
    )
  })
  await act(async () => {})
  return container.textContent ?? ""
}

const toggleButton = () =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes("本周为什么这样练"),
  )

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

describe("计划页解释卡", () => {
  it("默认收起，展开后四块标题与内容都可见", async () => {
    const text = await renderPlan(planResponse(explanationWithAdjustment("increase")))

    expect(text).toContain("本周为什么这样练")
    expect(text).toContain("展开")
    expect(text).not.toContain("本周目标")

    await act(async () => {
      toggleButton()?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    const expanded = container.textContent ?? ""
    for (const title of ["本周目标", "重点来源", "训练量", "调整说明"]) {
      expect(expanded).toContain(title)
    }
    expect(expanded).toContain("本周目标：增肌")
    expect(expanded).toContain("本周上调强度")
    expect(expanded).toContain("上肢推")
    expect(expanded).toContain("收起")
  })

  it("页头不再出现难度系数这类技术值", async () => {
    const text = await renderPlan(planResponse(explanationWithAdjustment("keep")))

    expect(text).not.toContain("难度系数")
    expect(text).toContain("本周从 2026-03-16 开始")
    for (const slang of ["老铁", "兄弟", "走起", "干就完了"]) {
      expect(text).not.toContain(slang)
    }
  })

  it("旧计划没有解释数据时显示「生成于解释字段上线之前」，不留空白块", async () => {
    await renderPlan(planResponse(null))
    await act(async () => {
      toggleButton()?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    const text = container.textContent ?? ""
    expect(text).toContain("生成于解释字段上线之前")
    expect(text).toContain("按当前档案推断")
    expect(text).toContain("训练量")
    // 四块都有非空文案：不出现空占位符。
    expect(text).not.toContain("undefined")
    expect(text).not.toContain("{{")
  })

  it("有解释但本周没有调整时显示「本周还没有调整记录」", async () => {
    await renderPlan(
      planResponse({
        generation: { body_type: "mesomorph", profile_goal: "减脂" },
        latest_adjustment: null,
      }),
    )
    await act(async () => {
      toggleButton()?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    const text = container.textContent ?? ""
    expect(text).toContain("本周还没有调整记录")
    expect(text).not.toContain("生成于解释字段上线之前")
    expect(text).not.toContain("undefined")
    expect(text).not.toContain("{{")
    for (const slang of ["老铁", "兄弟", "走起", "干就完了"]) {
      expect(text).not.toContain(slang)
    }
  })

  it("方向为保持时显示「本周保持原强度」", async () => {
    await renderPlan(planResponse(explanationWithAdjustment("keep")))
    await act(async () => {
      toggleButton()?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    const text = container.textContent ?? ""
    expect(text).toContain("本周保持原强度")
    expect(text).not.toContain("本周还没有调整记录")
    expect(text).not.toContain("生成于解释字段上线之前")
    expect(text).not.toContain("undefined")
    expect(text).not.toContain("{{")
    for (const slang of ["老铁", "兄弟", "走起", "干就完了"]) {
      expect(text).not.toContain(slang)
    }
  })
})
