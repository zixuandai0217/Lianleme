// @vitest-environment jsdom
/* Lazy-loading + degradation behaviour of the 3D muscle heatmap.
 *
 * The real WebGL runtime is replaced by a fake so jsdom never needs a GPU. The
 * test asserts the contract: no three runtime / model request before the user
 * opens the heatmap, the list stays readable when the device is unsupported or
 * loading fails, and a new scene updates the existing runtime instead of
 * remounting it.
 */
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const heatmap = vi.hoisted(() => ({
  probe: vi.fn(),
  create: vi.fn(),
}))

const threeRuntime = vi.hoisted(() => ({ loads: 0 }))

// If anything imports three eagerly, this factory records it. The heatmap must
// stay model- and runtime-free until the user opens it.
vi.mock("three", () => {
  threeRuntime.loads += 1
  return {}
})

vi.mock("@/lib/muscle-heatmap-3d", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/muscle-heatmap-3d")>()
  return {
    ...actual,
    probeHeatmapCapability: heatmap.probe,
    createMuscleHeatmapRuntime: heatmap.create,
  }
})

const api = vi.hoisted(() => ({
  startAnalyze: vi.fn(),
  getAnalyzeResult: vi.fn(),
  getAnalysisHistory: vi.fn(),
  getCurrentPlan: vi.fn(),
  generatePlan: vi.fn(),
}))

vi.mock("@/api", () => api)

const analysisResult = {
  body_type: "mesomorph",
  body_fat_range: "15-20%",
  weak_muscles: ["背"],
  strengths: ["腿"],
  muscle_scores: { chest: 7, upper_back: 6, core: 4 },
  summary: "胸部与上背表现稳定，核心需要加强。",
}

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    userId: 1,
    user: {
      id: 1,
      openid: "heatmap-tester",
      api_key_status: { has_key: true, provider: "qwen" },
      profile: { goal: "增肌" },
      body_analysis: analysisResult,
    },
    refreshUser: async () => undefined,
  }),
}))

import { MuscleHeatmap3D } from "@/components/muscle-heatmap-3d"
import AnalysisPage from "@/pages/analysis"

let root: Root | null = null
let container: HTMLDivElement
let fetchSpy: ReturnType<typeof vi.fn>

const flush = async () => {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

const mount = async (element: React.ReactNode) => {
  await act(async () => {
    root?.render(element)
  })
  await flush()
}

const findButton = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes(label),
  )

const click = async (element: Element) => {
  await act(async () => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true }))
  })
  await flush()
}

const fakeRuntime = () => ({
  compare: false,
  update: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
})

beforeEach(() => {
  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

  fetchSpy = vi.fn()
  vi.stubGlobal("fetch", fetchSpy)

  heatmap.probe.mockReset()
  heatmap.create.mockReset()
  threeRuntime.loads = 0

  api.startAnalyze.mockReset()
  api.getAnalyzeResult.mockReset()
  api.getAnalysisHistory.mockReset()
  api.getCurrentPlan.mockReset()
  api.generatePlan.mockReset()

  api.getAnalysisHistory.mockResolvedValue({
    records: [
      {
        id: 11,
        created_at: "2026-01-02T10:00:00Z",
        result: {
          ...analysisResult,
          muscle_scores: { chest: 5, upper_back: 5, core: 4 },
        },
      },
    ],
    total: 1,
  })
  api.getCurrentPlan.mockResolvedValue({ plan: undefined })

  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  if (root) {
    await act(async () => root?.unmount())
  }
  root = null
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe("MuscleHeatmap3D fallback", () => {
  it("renders the score list and capability notice without importing three", async () => {
    heatmap.probe.mockReturnValue("unsupported")

    await mount(
      <MuscleHeatmap3D scores={{ chest: 7, upper_back: 6 }} weakMuscles={["背"]} />,
    )

    expect(container.textContent).toContain("3D 视图未启用")
    expect(container.textContent).toContain("当前设备不支持 3D 视图")
    expect(container.textContent).toContain("胸部")
    expect(container.textContent).toContain("7/10")
    expect(container.textContent).toContain("未评估")
    expect(heatmap.create).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(threeRuntime.loads).toBe(0)
  })

  it("degrades to the list when there are no scores at all", async () => {
    await mount(<MuscleHeatmap3D scores={null} />)

    expect(container.textContent).toContain("这次分析没有部位评分")
    expect(heatmap.probe).not.toHaveBeenCalled()
    expect(heatmap.create).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("shows 3D 视图暂不可用 and only retries when the user asks", async () => {
    heatmap.probe.mockReturnValue("supported")
    heatmap.create
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(fakeRuntime())

    await mount(<MuscleHeatmap3D scores={{ chest: 7 }} />)

    expect(container.textContent).toContain("3D 视图暂不可用")
    expect(container.textContent).toContain("胸部")
    expect(container.textContent).toContain("7/10")
    expect(heatmap.create).toHaveBeenCalledTimes(1)

    const retry = findButton("重试 3D 视图")
    expect(retry).toBeTruthy()
    await click(retry!)

    expect(heatmap.create).toHaveBeenCalledTimes(2)
    expect(container.textContent).toContain("点击模型上的肌肉区域查看分数")
  })

  it("updates the existing runtime when a new scene arrives instead of remounting", async () => {
    heatmap.probe.mockReturnValue("supported")
    const runtime = fakeRuntime()
    heatmap.create.mockResolvedValue(runtime)

    await mount(<MuscleHeatmap3D scores={{ chest: 2 }} />)
    expect(heatmap.create).toHaveBeenCalledTimes(1)

    await mount(<MuscleHeatmap3D scores={{ chest: 9 }} />)
    await flush()

    expect(heatmap.create).toHaveBeenCalledTimes(1)
    const latest = runtime.update.mock.calls.at(-1)?.[0] as {
      scene: { byRegion: { chest: { score: number } } }
    }
    expect(latest.scene.byRegion.chest.score).toBe(9)
  })
})

describe("AnalysisPage 3D heatmap entry", () => {
  it("does not probe WebGL or request the model before the heatmap is opened", async () => {
    await mount(
      <MemoryRouter>
        <AnalysisPage />
      </MemoryRouter>,
    )

    expect(container.textContent).toContain("胸部与上背表现稳定，核心需要加强。")
    expect(findButton("部位评分详情")).toBeTruthy()
    expect(findButton("3D 热力图")).toBeTruthy()
    expect(heatmap.probe).not.toHaveBeenCalled()
    expect(heatmap.create).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(threeRuntime.loads).toBe(0)
    expect(container.querySelector("[data-muscle-heatmap]")).toBeNull()
  })

  it("keeps the text result and score list visible when WebGL is unavailable", async () => {
    heatmap.probe.mockReturnValue("unsupported")

    await mount(
      <MemoryRouter>
        <AnalysisPage />
      </MemoryRouter>,
    )

    const toggle = findButton("3D 热力图")
    expect(toggle).toBeTruthy()
    await click(toggle!)

    expect(container.textContent).toContain("胸部与上背表现稳定，核心需要加强。")
    expect(findButton("部位评分详情")).toBeTruthy()
    expect(container.textContent).toContain("当前设备不支持 3D 视图")
    expect(container.textContent).toContain("7/10")
    expect(heatmap.create).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(threeRuntime.loads).toBe(0)
  })
})

describe("probeHeatmapCapability", () => {
  const actualModule = async () =>
    vi.importActual<typeof import("@/lib/muscle-heatmap-3d")>("@/lib/muscle-heatmap-3d")

  it("tries webgl2 then webgl and reports unsupported when both are missing", async () => {
    const actual = await actualModule()
    const getContext = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(null as never)

    expect(actual.probeHeatmapCapability()).toBe("unsupported")
    expect(getContext).toHaveBeenNthCalledWith(1, "webgl2")
    expect(getContext).toHaveBeenNthCalledWith(2, "webgl")
    getContext.mockRestore()
  })

  it("reports supported when a context is created, and probe-failed when probing throws", async () => {
    const actual = await actualModule()
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext")

    getContext.mockReturnValueOnce({} as WebGL2RenderingContext)
    expect(actual.probeHeatmapCapability()).toBe("supported")

    getContext.mockImplementation(() => {
      throw new Error("blocked")
    })
    expect(actual.probeHeatmapCapability()).toBe("probe-failed")
    getContext.mockRestore()
  })
})
