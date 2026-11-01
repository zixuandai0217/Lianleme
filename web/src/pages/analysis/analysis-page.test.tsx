// @vitest-environment jsdom
/* 分析页终止态行为：过期后立即停轮询，并把「重新发起」交给用户。 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  startAnalyze: vi.fn(),
  getAnalyzeResult: vi.fn(),
  getAnalysisHistory: vi.fn(),
  getCurrentPlan: vi.fn(),
  generatePlan: vi.fn(),
}))

const refreshUser = vi.hoisted(() => vi.fn(async () => undefined))

vi.mock("@/api", () => api)
vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    userId: 1,
    user: {
      id: 1,
      openid: "analysis-tester",
      api_key_status: { has_key: true, provider: "qwen" },
      profile: { goal: "减脂" },
    },
    refreshUser,
  }),
}))

import AnalysisPage from "@/pages/analysis"

const pendingTask = {
  task_id: "task-1",
  status: "pending" as const,
  poll_interval_ms: 1000,
}

const expiredTask = {
  task_id: "task-1",
  status: "expired" as const,
  expires_at: "2026-01-01T00:10:00Z",
}

let root: Root | null
let container: HTMLDivElement

class ImmediateFileReader {
  result: string | ArrayBuffer | null = null
  onload: ((event: { target: { result: string | ArrayBuffer | null } }) => void) | null = null

  readAsDataURL() {
    this.result = "data:image/png;base64,eA=="
    this.onload?.({ target: this })
  }
}

const findButton = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes(label),
  )

const flush = async () => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

const mountPage = async () => {
  await act(async () => {
    root?.render(
      <MemoryRouter>
        <AnalysisPage />
      </MemoryRouter>,
    )
  })
  await flush()
}

const submitPhoto = async () => {
  const input = container.querySelector<HTMLInputElement>("#analysis-photo")
  if (!input) throw new Error("photo input not found")
  const file = new File(["photo"], "photo.png", { type: "image/png" })
  Object.defineProperty(input, "files", { configurable: true, value: [file] })

  await act(async () => {
    input.dispatchEvent(new Event("change", { bubbles: true }))
  })

  const startButton = findButton("开始分析")
  if (!startButton) throw new Error("start button not found")
  await act(async () => {
    startButton.dispatchEvent(new MouseEvent("click", { bubbles: true }))
  })
  await flush()
  await flush()
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.useFakeTimers()
  vi.stubGlobal("FileReader", ImmediateFileReader)

  api.startAnalyze.mockResolvedValue(pendingTask)
  api.getAnalyzeResult.mockResolvedValue(expiredTask)
  api.getAnalysisHistory.mockResolvedValue({ records: [], total: 0 })
  api.getCurrentPlan.mockResolvedValue({ plan: undefined })

  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe("AnalysisPage task polling", () => {
  it("stops polling as soon as the task is expired and offers a restart", async () => {
    await mountPage()
    await submitPhoto()

    expect(api.getAnalyzeResult).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain("分析任务已过期")
    expect(container.textContent).toContain("重新发起分析")
    expect(container.textContent).not.toContain("Traceback")

    // 终止态之后即使经过多个轮询周期，也不再发请求。
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(api.getAnalyzeResult).toHaveBeenCalledTimes(1)
  })

  it("stops polling when execution retries are exhausted and offers a restart", async () => {
    api.getAnalyzeResult.mockResolvedValue({
      task_id: "task-1",
      status: "failed",
      error: {
        code: "retry_exhausted",
        message: "这次分析已经用尽重试次数。",
        retryable: false,
      },
    })

    await mountPage()
    await submitPhoto()

    expect(api.getAnalyzeResult).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain("多次重试后仍未完成分析")
    expect(container.textContent).toContain("重新发起分析")

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(api.getAnalyzeResult).toHaveBeenCalledTimes(1)
  })
})
