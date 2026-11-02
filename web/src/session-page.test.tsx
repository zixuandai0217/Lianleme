// @vitest-environment jsdom
/* 训练会话页的用户可见行为：当前动作/进度、完成一组后的倒计时、跳过原因、收尾打卡与空态。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { SessionExercise, TodayWorkout, WorkoutSessionView } from "@/api/types"

const state = vi.hoisted(() => ({
  current: null as WorkoutSessionView | null,
  today: null as TodayWorkout | null,
  next: null as WorkoutSessionView | null,
  calls: [] as string[],
}))

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ userId: 1, user: { id: 1, openid: "u-1" } }),
}))

vi.mock("@/api", () => ({
  getCurrentWorkoutSession: () => Promise.resolve(state.current),
  getTodayWorkout: () => Promise.resolve(state.today),
  startWorkoutSession: () => {
    state.calls.push("start")
    return Promise.resolve(state.next)
  },
  completeSessionSet: (sessionId: string, exerciseIndex: number, setIndex: number) => {
    state.calls.push(`set:${sessionId}:${exerciseIndex}:${setIndex}`)
    return Promise.resolve(state.next)
  },
  skipSessionExercise: (sessionId: string, exerciseIndex: number, reason: string) => {
    state.calls.push(`skip:${sessionId}:${exerciseIndex}:${reason}`)
    return Promise.resolve(state.next)
  },
}))

import SessionPage from "@/pages/session"

let root: Root | null
let container: HTMLDivElement

function exercise(overrides: Partial<SessionExercise> = {}): SessionExercise {
  return {
    index: 0,
    order: 1,
    name: "卧推",
    sets: 4,
    reps: "8-12",
    weight_suggestion: "体重 40%",
    tips: "肩胛收紧",
    rest_seconds: 2,
    completed_sets: 2,
    skipped: false,
    skip_reason: null,
    status: "pending",
    target_set_number: 3,
    ...overrides,
  }
}

function session(overrides: Partial<WorkoutSessionView> = {}): WorkoutSessionView {
  return {
    session_id: "ws_1",
    user_id: 1,
    status: "in_progress",
    session_date: "2026-03-18",
    started_at: "2026-03-18T12:00:00Z",
    last_activity_at: "2026-03-18T12:05:00Z",
    progress: { completed_sets: 2, total_sets: 7, percent: 29 },
    exercises: [exercise(), exercise({ index: 1, order: 2, name: "划船", sets: 3 })],
    current_exercise: exercise(),
    next_exercise: exercise({ index: 1, order: 2, name: "划船", sets: 3 }),
    finished: false,
    can_checkin: false,
    ...overrides,
  }
}

async function renderPage() {
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={["/session"]}>
        <Routes>
          <Route path="/session" element={<SessionPage />} />
          <Route path="/" element={<div>首页打卡弹窗</div>} />
        </Routes>
      </MemoryRouter>,
    )
  })
  await act(async () => {})
  return container.textContent ?? ""
}

// Radix Dialog 渲染在 portal 里，按钮必须从整个 document 查询。
const buttons = () => Array.from(document.querySelectorAll("button"))

const findButton = (fragment: string) =>
  buttons().find((button) => button.textContent?.includes(fragment))

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
  state.current = session()
  state.today = null
  state.next = null
  state.calls = []
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  vi.useRealTimers()
})

describe("训练会话页", () => {
  it("展示当前动作、组内进度与整体进度（与服务端一致）", async () => {
    const text = await renderPage()

    expect(text).toContain("卧推")
    expect(text).toContain("4 组 × 8-12")
    expect(text).toContain("第 3/4 组")
    expect(text).toContain("已练 2/7 组")
    expect(text).toContain("下一个动作：划船")
  })

  it("完成一组后进度更新，并进入倒计时；倒计时结束回到训练态", async () => {
    vi.useFakeTimers()
    const completed = session({
      progress: { completed_sets: 3, total_sets: 7, percent: 43 },
      current_exercise: exercise({ completed_sets: 3, target_set_number: 4 }),
      exercises: [exercise({ completed_sets: 3, target_set_number: 4 })],
    })
    state.next = completed
    await renderPage()

    await act(async () => {
      findButton("完成一组")?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await act(async () => {})

    expect(state.calls).toContain("set:ws_1:0:2")
    expect(container.textContent).toContain("已练 3/7 组")
    expect(container.textContent).toContain("休息 00:02")

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(container.textContent).not.toContain("休息 00:0")
    expect(findButton("完成一组")).toBeTruthy()
  })

  it("跳过动作必须选择原因，提交后显示已跳过且不增加完成组数", async () => {
    const skipped = session({
      exercises: [
        exercise({ status: "skipped", skipped: true, skip_reason: "器械被占", target_set_number: null }),
        exercise({ index: 1, order: 2, name: "划船", sets: 3 }),
      ],
      current_exercise: exercise({ index: 1, order: 2, name: "划船", sets: 3 }),
      next_exercise: null,
    })
    state.next = skipped
    await renderPage()

    await act(async () => {
      findButton("跳过这个动作")?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    const confirmBefore = findButton("确认跳过")
    expect(confirmBefore?.hasAttribute("disabled")).toBe(true)

    await act(async () => {
      findButton("器械被占")?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await act(async () => {
      findButton("确认跳过")?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await act(async () => {})

    expect(state.calls).toContain("skip:ws_1:0:器械被占")
    expect(container.textContent).toContain("已跳过")
    expect(container.textContent).toContain("已练 2/7 组")
  })

  it("全部动作处理完后出现「收尾并打卡」，点击进入打卡流程", async () => {
    state.current = session({
      finished: true,
      can_checkin: true,
      current_exercise: null,
      next_exercise: null,
      progress: { completed_sets: 7, total_sets: 7, percent: 100 },
    })
    await renderPage()

    const checkin = findButton("收尾并打卡")
    expect(checkin).toBeTruthy()

    await act(async () => {
      checkin?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    expect(container.textContent).toContain("首页打卡弹窗")
  })

  it("未处理完时不出现收尾打卡入口", async () => {
    await renderPage()

    expect(findButton("收尾并打卡")).toBeUndefined()
  })

  it("刷新后从服务端恢复进度，不归零", async () => {
    await renderPage()
    const first = container.textContent

    await act(async () => root?.unmount())
    root = null
    container.remove()
    container = document.createElement("div")
    document.body.append(container)
    root = createRoot(container)

    const second = await renderPage()
    expect(second).toBe(first)
    expect(second).toContain("已练 2/7 组")
  })

  it("休息日与无计划是两种空态，且都不显示开始训练", async () => {
    state.current = null
    state.today = { status: "rest_day", is_rest_day: true, message: "今日休息，好好恢复" }
    let text = await renderPage()
    expect(text).toContain("今天是恢复日")
    expect(findButton("开始训练")).toBeUndefined()

    await act(async () => root?.unmount())
    root = null
    container.remove()
    container = document.createElement("div")
    document.body.append(container)
    root = createRoot(container)

    state.today = { status: "no_plan", is_rest_day: false }
    text = await renderPage()
    expect(text).toContain("还没有本周训练计划")
    expect(findButton("开始训练")).toBeUndefined()
  })

  it("训练日且未开始时可点开始训练进入会话", async () => {
    state.current = null
    state.today = {
      status: "training_day",
      is_rest_day: false,
      focus: "胸背",
      exercises: [exercise()],
    }
    state.next = session()
    await renderPage()

    await act(async () => {
      findButton("开始训练")?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })
    await act(async () => {})

    expect(state.calls).toContain("start")
    expect(container.textContent).toContain("卧推")
  })
})
