/* Pure behaviour + build-time asset contract for the 3D muscle heatmap.
 *
 * No WebGL and no three.js imports here: the render layer is exercised by the
 * jsdom tests, while this file locks the decisions the renderer depends on
 * (orbit clamps, layout, emissive colour, cache, GLB naming/budget).
 */
import { existsSync, readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  MUSCLE_REGIONS,
  NEUTRAL_INTENSITY,
  buildHeatmapScene,
  compareHeatmaps,
} from "./muscle-heatmap"
import {
  DEFAULT_DISTANCE,
  MAX_DISTANCE,
  MAX_MODEL_INSTANCES,
  MAX_POLAR_ANGLE,
  MIN_DISTANCE,
  MIN_POLAR_ANGLE,
  MODEL_LOAD_TIMEOUT_MS,
  MODEL_URL,
  annotationForDiff,
  applyVisualToMaterial,
  buildAriaSummary,
  clampOrbit,
  describeRegion,
  emissiveForVisual,
  hueToRgb,
  layoutForWidth,
  loadMuscleBodyBinary,
  modelInstanceCount,
  resetMuscleBodyCache,
  weakRegionsFromAnalysis,
  withTimeout,
} from "./lib/muscle-heatmap-3d"
import { buildMuscleBodyGlb, MUSCLE_REGION_NAMES } from "../scripts/generate-muscle-body-glb.mjs"

const GLB_PATH = fileURLToPath(new URL("../public/models/muscle-body.glb", import.meta.url))
const MAX_GLB_BYTES = 2 * 1024 * 1024

const source = (relativePath: string) =>
  readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8")

describe("lazy three boundary", () => {
  it("keeps the three runtime behind dynamic imports", () => {
    const runtimeSource = source("./lib/muscle-heatmap-3d.ts")
    const componentSource = source("./components/muscle-heatmap-3d.tsx")

    expect(runtimeSource).toContain('import("three")')
    expect(runtimeSource).toContain('import("three/examples/jsm/loaders/GLTFLoader.js")')
    expect(runtimeSource).not.toMatch(/from\s+["']three["']/)
    expect(componentSource).not.toMatch(/from\s+["']three["']/)
    expect(componentSource).not.toContain('import("three")')
  })
})

describe("layoutForWidth", () => {
  it("stacks the comparison on narrow viewports and splits on wide ones", () => {
    expect(layoutForWidth(320)).toBe("stacked")
    expect(layoutForWidth(719)).toBe("stacked")
    expect(layoutForWidth(720)).toBe("split")
    expect(layoutForWidth(1440)).toBe("split")
    expect(layoutForWidth(Number.NaN)).toBe("stacked")
  })
})

describe("clampOrbit", () => {
  it("keeps the camera outside the body and above the ground", () => {
    expect(clampOrbit({ distance: 0.2, polar: 0 }).distance).toBe(MIN_DISTANCE)
    expect(clampOrbit({ distance: 50, polar: Math.PI }).distance).toBe(MAX_DISTANCE)
    expect(clampOrbit({ distance: 0.2, polar: 0 }).polar).toBe(MIN_POLAR_ANGLE)
    expect(clampOrbit({ distance: 50, polar: Math.PI }).polar).toBe(MAX_POLAR_ANGLE)
    expect(MAX_POLAR_ANGLE).toBeLessThan(Math.PI / 2)
  })

  it("passes legal values through and falls back on non-finite input", () => {
    expect(clampOrbit({ distance: 4, polar: 1.1 })).toEqual({ distance: 4, polar: 1.1 })
    expect(clampOrbit({ distance: Number.NaN, polar: Number.NaN })).toEqual({
      distance: DEFAULT_DISTANCE,
      polar: 1.22,
    })
  })
})

describe("hueToRgb — ADR-0005 red-to-yellow ramp", () => {
  it("anchors red, orange and yellow", () => {
    expect(hueToRgb(0)).toEqual({ r: 1, g: 0, b: 0 })
    expect(hueToRgb(30)).toEqual({ r: 1, g: 0.5, b: 0 })
    expect(hueToRgb(60)).toEqual({ r: 1, g: 1, b: 0 })
  })

  it("wraps full turns and tolerates invalid hue", () => {
    expect(hueToRgb(360)).toEqual(hueToRgb(0))
    expect(hueToRgb(-30)).toEqual(hueToRgb(330))
    expect(hueToRgb(Number.NaN)).toEqual(hueToRgb(0))
  })
})

describe("emissiveForVisual", () => {
  it("uses the score intensity and hue for an evaluated region", () => {
    const visual = buildHeatmapScene({ chest: 7 }).byRegion.chest
    const emissive = emissiveForVisual(visual)

    expect(emissive.intensity).toBeCloseTo(0.7, 6)
    expect(emissive.r).toBeCloseTo(1, 6)
    expect(emissive.b).toBeCloseTo(0, 6)
  })

  it("never turns a missing region into a red zero-score region", () => {
    const visual = buildHeatmapScene({ chest: 7 }).byRegion.calves
    const emissive = emissiveForVisual(visual)

    expect(visual.evaluated).toBe(false)
    expect(emissive).toEqual({ r: 0.55, g: 0.55, b: 0.55, intensity: NEUTRAL_INTENSITY })
    expect(emissive.r).toBe(emissive.g)
    expect(emissive.g).toBe(emissive.b)
  })
})

describe("applyVisualToMaterial", () => {
  it("mutates the existing material in place so a new scene never remounts the canvas", () => {
    const calls: Array<[number, number, number]> = []
    const material = {
      emissive: {
        setRGB(red: number, green: number, blue: number) {
          calls.push([red, green, blue])
          return undefined
        },
      },
      emissiveIntensity: 0,
    }
    const first = buildHeatmapScene({ chest: 2 }).byRegion.chest
    const second = buildHeatmapScene({ chest: 9 }).byRegion.chest

    applyVisualToMaterial(material, first)
    expect(material.emissiveIntensity).toBeCloseTo(0.2, 6)

    applyVisualToMaterial(material, second)
    expect(material.emissiveIntensity).toBeCloseTo(0.9, 6)
    expect(calls).toHaveLength(2)
    expect(calls[0]).not.toEqual(calls[1])
  })
})

describe("weakRegionsFromAnalysis", () => {
  it("normalises Chinese analysis labels onto the twelve mesh regions", () => {
    const regions = weakRegionsFromAnalysis(["背", "左肩", "腿", "unknown"])

    expect([...regions].sort()).toEqual(["shoulders", "upper_back"])
  })

  it("returns an empty set when there are no weak muscles", () => {
    expect(weakRegionsFromAnalysis([]).size).toBe(0)
    expect(weakRegionsFromAnalysis(null).size).toBe(0)
  })
})

describe("describeRegion", () => {
  it("reports label, score band and weakness for an evaluated region", () => {
    const visual = buildHeatmapScene({ chest: 7 }).byRegion.chest
    const description = describeRegion(visual, true)

    expect(description.label).toBe("胸部")
    expect(description.scoreText).toBe("7/10 · 良好")
    expect(description.isWeak).toBe(true)
    expect(description.weakLabel).toBe("弱势肌群")
    expect(description.advice.length).toBeGreaterThan(0)
    expect(description.ariaLabel).toContain("弱势肌群")
  })

  it("marks an unevaluated region as 未评估 instead of zero", () => {
    const visual = buildHeatmapScene({ chest: 7 }).byRegion.calves
    const description = describeRegion(visual, false)

    expect(description.evaluated).toBe(false)
    expect(description.scoreText).toBe("未评估")
    expect(description.weakLabel).toBeNull()
  })
})

describe("buildAriaSummary", () => {
  it("describes evaluated and missing regions for screen readers", () => {
    const summary = buildAriaSummary(buildHeatmapScene({ chest: 7, upper_back: 6 }))

    expect(summary).toContain("胸部 7 分")
    expect(summary).toContain("上背 6 分")
    expect(summary).toContain("小腿 未评估")
  })
})

describe("annotationForDiff", () => {
  it("annotates the largest absolute change without a badge threshold", () => {
    expect(
      annotationForDiff(compareHeatmaps({ chest: 5, abs: 4 }, { chest: 7, abs: 3 })),
    ).toBe("变化最大：胸部 +2")
    expect(
      annotationForDiff(compareHeatmaps({ chest: 7 }, { chest: 6 })),
    ).toBe("变化最大：胸部 -1")
    expect(annotationForDiff(null)).toBeNull()
    expect(annotationForDiff(compareHeatmaps({ chest: 5 }, { chest: 5 }))).toBeNull()
  })
})

describe("modelInstanceCount", () => {
  it("never creates more than two bodies", () => {
    expect(modelInstanceCount(false)).toBe(1)
    expect(modelInstanceCount(true)).toBe(MAX_MODEL_INSTANCES)
    expect(MAX_MODEL_INSTANCES).toBe(2)
  })
})

describe("loadMuscleBodyBinary", () => {
  beforeEach(() => resetMuscleBodyCache())
  afterEach(() => resetMuscleBodyCache())

  it("fetches the GLB once per session and reuses the same promise", async () => {
    const buffer = new ArrayBuffer(8)
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      arrayBuffer: async () => buffer,
    })

    const first = loadMuscleBodyBinary(fetchMock as unknown as typeof fetch)
    const second = loadMuscleBodyBinary(fetchMock as unknown as typeof fetch)

    expect(first).toBe(second)
    await expect(first).resolves.toBe(buffer)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(MODEL_URL)
  })

  it("clears the cache after a failure so the explicit retry can fetch again", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, arrayBuffer: async () => new ArrayBuffer(0) })
      .mockResolvedValueOnce({ ok: true, status: 200, arrayBuffer: async () => new ArrayBuffer(4) })

    await expect(
      loadMuscleBodyBinary(fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("503")
    await expect(
      loadMuscleBodyBinary(fetchMock as unknown as typeof fetch),
    ).resolves.toBeInstanceOf(ArrayBuffer)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

describe("withTimeout", () => {
  it("resolves before the deadline and rejects with the timeout message after it", async () => {
    await expect(withTimeout(Promise.resolve("ok"), 1000)).resolves.toBe("ok")

    vi.useFakeTimers()
    try {
      const pending = withTimeout(new Promise(() => undefined), 50, "3D 模型加载超时")
      const assertion = expect(pending).rejects.toThrow("3D 模型加载超时")
      await vi.advanceTimersByTimeAsync(60)
      await assertion
    } finally {
      vi.useRealTimers()
    }
    expect(MODEL_LOAD_TIMEOUT_MS).toBeGreaterThan(0)
  })
})

interface ParsedGlb {
  bytes: Buffer
  magic: number
  version: number
  declaredLength: number
  json: {
    nodes?: Array<{ name?: string; mesh?: number }>
    meshes?: Array<{ name?: string; primitives?: unknown[] }>
    materials?: unknown[]
    images?: unknown[]
    textures?: unknown[]
  }
  binLength: number
}

function parseGlb(bytes: Buffer): ParsedGlb {
  const magic = bytes.readUInt32LE(0)
  const version = bytes.readUInt32LE(4)
  const declaredLength = bytes.readUInt32LE(8)
  let offset = 12
  let json: ParsedGlb["json"] | null = null
  let binLength = 0

  while (offset + 8 <= bytes.byteLength) {
    const chunkLength = bytes.readUInt32LE(offset)
    const chunkType = bytes.readUInt32LE(offset + 4)
    const chunk = bytes.subarray(offset + 8, offset + 8 + chunkLength)
    if (chunkType === 0x4e4f534a) json = JSON.parse(chunk.toString("utf8")) as ParsedGlb["json"]
    if (chunkType === 0x004e4942) binLength = chunkLength
    offset += 8 + chunkLength
  }

  if (!json) throw new Error("GLB has no JSON chunk")
  return { bytes, magic, version, declaredLength, json, binLength }
}

describe("muscle body GLB asset contract", () => {
  it("exists and stays inside the 2MB budget", () => {
    expect(existsSync(GLB_PATH)).toBe(true)
    const bytes = readFileSync(GLB_PATH)
    expect(bytes.byteLength).toBeGreaterThan(0)
    expect(bytes.byteLength).toBeLessThanOrEqual(MAX_GLB_BYTES)
  })

  it("is a valid glTF 2.0 binary with a complete header and BIN chunk", () => {
    const parsed = parseGlb(readFileSync(GLB_PATH))

    expect(parsed.magic).toBe(0x46546c67)
    expect(parsed.version).toBe(2)
    expect(parsed.declaredLength).toBe(parsed.bytes.byteLength)
    expect(parsed.binLength).toBeGreaterThan(0)
  })

  it("carries exactly the twelve region names as node and mesh names", () => {
    const parsed = parseGlb(readFileSync(GLB_PATH))
    const expected = [...MUSCLE_REGIONS].sort()
    const nodeNames = (parsed.json.nodes ?? []).map((node) => node.name).sort()
    const meshNames = (parsed.json.meshes ?? []).map((mesh) => mesh.name).sort()

    expect(nodeNames).toEqual(expected)
    expect(meshNames).toEqual(expected)
    expect(parsed.json.nodes).toHaveLength(12)
    expect(parsed.json.meshes).toHaveLength(12)
    expect((parsed.json.nodes ?? []).every((node) => typeof node.mesh === "number")).toBe(true)
    expect([...MUSCLE_REGION_NAMES].sort()).toEqual(expected)
  })

  it("ships no external textures or extra scene nodes", () => {
    const parsed = parseGlb(readFileSync(GLB_PATH))

    expect(parsed.json.images ?? []).toHaveLength(0)
    expect(parsed.json.textures ?? []).toHaveLength(0)
    expect(parsed.json.materials).toHaveLength(12)
  })

  it("is reproducible byte-for-byte from the committed generator", () => {
    const generated = buildMuscleBodyGlb()
    const committed = readFileSync(GLB_PATH)

    expect(Buffer.from(generated).equals(committed)).toBe(true)
  })
})
