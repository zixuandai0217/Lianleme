// @vitest-environment jsdom
/* Page-level wiring for turn notices: bubble vs notice vs speech queue. */
import { act, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import CoachPage from "@/pages/coach"
import type { CoachTurnState } from "@/lib/coach-protocol"

const apiMocks = vi.hoisted(() => ({
  getChatHistory: vi.fn(),
  getTodayWorkout: vi.fn(),
  getCoachTTSStatus: vi.fn(),
}))

const authState = vi.hoisted(() => ({
  user: { id: 1, nickname: "测试用户" },
}))

const voice = vi.hoisted(() => ({
  play: vi.fn<(id: string, text: string) => Promise<void>>(),
  pause: vi.fn(),
  prepare: vi.fn(),
  status: "idle" as const,
  activeId: null,
  error: null,
  analyser: null,
  viseme: "X" as const,
}))

const streamMock = vi.hoisted(() => vi.fn())

vi.mock("@/api", () => apiMocks)
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => authState }))
vi.mock("@/hooks/use-coach-voice", () => ({ useCoachVoice: () => voice }))
vi.mock("@/lib/coach-protocol", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/coach-protocol")>()
  return { ...actual, streamCoachTurn: streamMock }
})
vi.mock("@/components/digital-coach", () => ({ DigitalCoach: () => null }))
vi.mock("@/components/voice-waveform", () => ({ VoiceWaveform: () => null }))
vi.mock("@/components/ui/tooltip", async () => {
  const { createElement, Fragment } = await import("react")
  const PassThrough = ({ children }: { children?: ReactNode }) =>
    createElement(Fragment, null, children)
  return {
    Tooltip: PassThrough,
    TooltipTrigger: PassThrough,
    TooltipContent: () => null,
  }
})

let root: Root | null
let container: HTMLDivElement

function turnState(overrides: Partial<CoachTurnState>): CoachTurnState {
  return {
    status: "idle",
    turnId: "turn-1",
    started: true,
    body: "",
    coachState: "guide",
    actions: [],
    finishReason: null,
    error: null,
    ignoredTurnId: null,
    ...overrides,
  }
}

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function mountPage(): Promise<void> {
  await act(async () => {
    root?.render(<CoachPage />)
  })
  await flush()
}

async function sendViaQuickAction(): Promise<void> {
  const action = Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes("根据今天的计划"),
  )
  expect(action, "default quick action should be available").toBeTruthy()
  await act(async () => {
    action?.click()
  })
  await flush()
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.clearAllMocks()
  apiMocks.getChatHistory.mockResolvedValue({ messages: [], total: 0 })
  apiMocks.getTodayWorkout.mockResolvedValue(null)
  apiMocks.getCoachTTSStatus.mockResolvedValue({
    available: true,
    lip_sync_available: false,
  })
  streamMock.mockReset()
  voice.play.mockClear()
  voice.pause.mockClear()
  voice.prepare.mockClear()

  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    configurable: true,
    value: vi.fn(),
  })

  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("coach page turn notices", () => {
  it("renders a provider error as its own notice and never speaks it", async () => {
    streamMock.mockResolvedValue(
      turnState({
        status: "error",
        finishReason: "error",
        body: "先来一组",
        error: { code: "provider_unavailable", message: "检查你的 API Key 配置。" },
      }),
    )

    await mountPage()
    await sendViaQuickAction()

    const notice = container.querySelector('[data-coach-notice="error"]')
    expect(notice?.textContent).toContain("检查你的 API Key 配置。")
    expect(notice?.closest("article")).toBeNull()
    expect(container.querySelector('[role="log"]')?.textContent).toContain("先来一组")
    const bubbles = Array.from(container.querySelectorAll("article"))
    expect(
      bubbles.some((bubble) => bubble.textContent?.includes("检查你的 API Key 配置。")),
    ).toBe(false)
    expect(voice.play).not.toHaveBeenCalled()
  })

  it("keeps partial text and shows 连接中断 outside the bubble for a truncated turn", async () => {
    streamMock.mockResolvedValue(
      turnState({ status: "idle", finishReason: "truncated", body: "半句话" }),
    )

    await mountPage()
    await sendViaQuickAction()

    const notice = container.querySelector('[data-coach-notice="truncated"]')
    expect(notice?.textContent).toContain("连接中断")
    expect(notice?.closest("article")).toBeNull()
    const bubbles = Array.from(container.querySelectorAll("article"))
    expect(bubbles.some((bubble) => bubble.textContent?.includes("半句话"))).toBe(true)
    expect(voice.play).toHaveBeenCalledWith(expect.any(String), "半句话")
    expect(voice.play.mock.calls.every(([, text]) => text !== "连接中断，回复可能不完整。")).toBe(true)
  })

  it("shows only the notice instead of an empty bubble when truncation has no body", async () => {
    streamMock.mockResolvedValue(
      turnState({ status: "idle", finishReason: "truncated", body: "" }),
    )

    await mountPage()
    await sendViaQuickAction()

    expect(container.querySelector('[data-coach-notice="truncated"]')?.textContent).toContain(
      "连接中断",
    )
    // Only the user message remains: the empty assistant bubble was removed.
    expect(container.querySelectorAll("article")).toHaveLength(1)
    expect(container.textContent).not.toContain("正在思考")
    expect(voice.play).not.toHaveBeenCalled()
  })

  it("produces no notice, no error alert, and no speech for a user abort", async () => {
    streamMock.mockRejectedValue(new DOMException("Aborted", "AbortError"))

    await mountPage()
    await sendViaQuickAction()

    expect(container.querySelector("[data-coach-notice]")).toBeNull()
    expect(container.querySelector('[role="alert"]')).toBeNull()
    expect(container.textContent).not.toContain("正在思考")
    expect(voice.play).not.toHaveBeenCalled()
  })
})
