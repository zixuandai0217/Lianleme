// @vitest-environment jsdom
/* Exercise the mounted 2D coach across visemes, variants, motion preferences, and blink timing. */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { DigitalCoach, type DigitalCoachState } from "@/components/digital-coach"
import type { CoachViseme } from "@/components/coach-lip-sync"

let root: Root | null
let container: HTMLDivElement

// Mount the coach with a deterministic operating-system motion preference.
async function renderCoach({
  state = "idle",
  variant = "stage",
  viseme = "X",
  reducedMotion = false,
}: {
  state?: DigitalCoachState
  variant?: "stage" | "portrait"
  viseme?: CoachViseme
  reducedMotion?: boolean
} = {}) {
  vi.stubGlobal("matchMedia", vi.fn(() => ({
    matches: reducedMotion,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })))

  await act(async () => {
    root?.render(
      <DigitalCoach
        state={state}
        variant={variant}
        viseme={viseme}
        ariaLabel="数字教练"
      />,
    )
  })
}

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.useFakeTimers()
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
  vi.restoreAllMocks()
})

describe("DigitalCoach 2D renderer", () => {
  it("renders the current stage viseme without a canvas or frame loop", async () => {
    vi.stubGlobal("requestAnimationFrame", vi.fn())
    await renderCoach({ state: "speaking", viseme: "D" })

    const host = container.querySelector<HTMLElement>("[data-coach-renderer]")
    const mouth = container.querySelector<HTMLImageElement>('[data-coach-layer="mouth"]')
    expect(host?.dataset.coachRenderer).toBe("layered-2d")
    expect(host?.dataset.viseme).toBe("D")
    expect(mouth?.getAttribute("src")).toBe("/coach/v2/face/mouth-D.webp")
    expect(container.querySelector("canvas")).toBeNull()
    expect(requestAnimationFrame).not.toHaveBeenCalled()
  })

  it("renders every A-H/X stage mouth from the shared aligned asset set", async () => {
    const visemes: CoachViseme[] = ["A", "B", "C", "D", "E", "F", "G", "H", "X"]

    for (const viseme of visemes) {
      await renderCoach({ state: "speaking", viseme })
      const mouth = container.querySelector<HTMLImageElement>('[data-coach-layer="mouth"]')
      expect(mouth?.getAttribute("src")).toBe(`/coach/v2/face/mouth-${viseme}.webp`)
    }
  })

  it("keeps face layers hidden until the body image is ready", async () => {
    await renderCoach({ state: "speaking", viseme: "D" })

    const body = container.querySelector<HTMLImageElement>('[data-coach-layer="body"]')
    const faceRig = container.querySelector<HTMLElement>('[data-face-rig="layered"]')
    expect(body?.getAttribute("src")).toBe("/coach/v2/coach-base.webp")
    expect(faceRig?.className).toContain("opacity-0")

    await act(async () => body?.dispatchEvent(new Event("load")))
    expect(faceRig?.className).toContain("opacity-100")
  })

  it("falls back to the previous static coach without mismatched face layers", async () => {
    await renderCoach({ state: "speaking", viseme: "D" })

    const primaryBody = container.querySelector<HTMLImageElement>('[data-coach-layer="body"]')
    await act(async () => primaryBody?.dispatchEvent(new Event("error")))

    const fallbackBody = container.querySelector<HTMLImageElement>('[data-coach-layer="body"]')
    expect(fallbackBody?.getAttribute("src")).toBe("/coach/rock-coach.webp")
    await act(async () => fallbackBody?.dispatchEvent(new Event("load")))

    const host = container.querySelector<HTMLElement>("[data-coach-renderer]")
    expect(host?.dataset.assetStatus).toBe("fallback")
    expect(container.querySelector('[data-face-rig="layered"]')).toBeNull()
  })

  it.each([
    {
      label: "mouth",
      props: { state: "speaking" as const, viseme: "D" as CoachViseme },
      failedSelector: '[data-coach-layer="mouth"]',
      survivorSelector: '[data-coach-layer="eyes-closed"]',
    },
    {
      label: "blink",
      props: { state: "idle" as const },
      failedSelector: '[data-coach-layer="eyes-closed"]',
      survivorSelector: '[data-coach-layer="mouth"]',
    },
    {
      label: "thinking brow",
      props: { state: "thinking" as const },
      failedSelector: '[data-coach-layer="brow-thinking"]',
      survivorSelector: '[data-coach-layer="eyes-closed"]',
    },
  ])("removes only a failed $label layer", async ({ props, failedSelector, survivorSelector }) => {
    await renderCoach(props)

    const body = container.querySelector<HTMLImageElement>('[data-coach-layer="body"]')
    await act(async () => body?.dispatchEvent(new Event("load")))
    const failedLayer = container.querySelector<HTMLImageElement>(failedSelector)
    expect(failedLayer).not.toBeNull()

    await act(async () => failedLayer?.dispatchEvent(new Event("error")))

    expect(container.querySelector(failedSelector)).toBeNull()
    expect(container.querySelector('[data-coach-layer="body"]')).not.toBeNull()
    expect(container.querySelector('[data-face-rig="layered"]')).not.toBeNull()
    expect(container.querySelector(survivorSelector)).not.toBeNull()
  })

  it("uses only compact expression overlays instead of replacing open eyes", async () => {
    await renderCoach({ state: "idle" })

    expect(container.querySelector('[data-coach-layer="eyes-open"]')).toBeNull()
    expect(container.querySelector('[data-coach-layer="pupils"]')).toBeNull()
    expect(container.querySelector<HTMLImageElement>('[data-coach-layer="eyes-closed"]')?.src).toContain(
      "/coach/v2/face/eyes-blink.webp",
    )
  })

  it("keeps the dashboard portrait closed and lightweight", async () => {
    await renderCoach({ state: "speaking", variant: "portrait", viseme: "H" })

    const host = container.querySelector<HTMLElement>("[data-coach-renderer]")
    expect(host?.dataset.viseme).toBe("X")
    expect(host?.dataset.blink).toBe("open")
    expect(host?.dataset.animationProfile).toBe("breath")
    expect(vi.getTimerCount()).toBe(0)
  })

  it("closes and reopens the stage eyes on the natural blink timer", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0)
    await renderCoach({ state: "idle" })

    const host = container.querySelector<HTMLElement>("[data-coach-renderer]")
    expect(host?.dataset.blink).toBe("open")
    expect(vi.getTimerCount()).toBe(1)

    await act(async () => vi.advanceTimersByTime(3_200))
    expect(host?.dataset.blink).toBe("closed")

    await act(async () => vi.advanceTimersByTime(92))
    expect(host?.dataset.blink).toBe("open")
  })

  it("resets a closed blink when stage animation is disabled and restored", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0)
    await renderCoach({ state: "idle", variant: "stage" })

    await act(async () => vi.advanceTimersByTime(3_200))
    expect(container.querySelector<HTMLElement>("[data-coach-renderer]")?.dataset.blink).toBe("closed")

    await renderCoach({ state: "idle", variant: "portrait" })
    await renderCoach({ state: "idle", variant: "stage" })
    expect(container.querySelector<HTMLElement>("[data-coach-renderer]")?.dataset.blink).toBe("open")
  })

  it("freezes the face and closes the mouth for reduced motion", async () => {
    await renderCoach({ state: "speaking", viseme: "H", reducedMotion: true })

    const host = container.querySelector<HTMLElement>("[data-coach-renderer]")
    expect(host?.dataset.motion).toBe("reduced")
    expect(host?.dataset.viseme).toBe("X")
    expect(host?.dataset.blink).toBe("open")
    expect(vi.getTimerCount()).toBe(0)
  })

  it("exposes every conversation state on the shared surface", async () => {
    const states: DigitalCoachState[] = ["idle", "listening", "thinking", "speaking", "error"]

    for (const state of states) {
      await renderCoach({ state })
      const host = container.querySelector<HTMLElement>("[data-coach-state]")
      expect(host?.dataset.coachState).toBe(state)
      expect(host?.dataset.animationProfile).toBe(state === "speaking" ? "speech" : "breath")
      expect(Boolean(container.querySelector('[data-coach-layer="brow-thinking"]'))).toBe(state === "thinking")
    }
  })
})
