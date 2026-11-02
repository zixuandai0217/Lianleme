import { describe, expect, it } from "vitest"

import {
  ASYMMETRY_THRESHOLD,
  DEFAULT_TOP_CHANGES,
  DIFF_BADGE_THRESHOLD,
  HEATMAP_LEGEND_HINT,
  MUSCLE_REGIONS,
  MUSCLE_REGION_LABELS,
  NEUTRAL_COLOR,
  NEUTRAL_INTENSITY,
  buildHeatmapScene,
  clampScore,
  compareHeatmaps,
  resolveHeatmapFallback,
  scoreToVisual,
  type MuscleRegion,
} from "./muscle-heatmap"

const REGION_CONTRACT: MuscleRegion[] = [
  "chest",
  "upper_back",
  "lower_back",
  "abs",
  "traps",
  "shoulders",
  "arms",
  "forearms",
  "glutes",
  "quads",
  "hamstrings",
  "calves",
]

const FULL_SCORES: Record<string, number> = Object.fromEntries(
  MUSCLE_REGIONS.map((region) => [region, 5]),
)

const scoreOf = (scores: unknown, region: MuscleRegion) =>
  buildHeatmapScene(scores).byRegion[region].score

describe("muscle heatmap region contract", () => {
  it("exports the twelve ADR-0005 mesh names in render order", () => {
    expect([...MUSCLE_REGIONS]).toEqual(REGION_CONTRACT)
    expect(Object.keys(MUSCLE_REGION_LABELS).sort()).toEqual([...REGION_CONTRACT].sort())
  })
})

describe("scoreToVisual — ADR-0005 score to glow mapping", () => {
  for (let score = 0; score <= 10; score += 1) {
    it(`maps integer score ${score} to linear intensity and hue`, () => {
      const visual = scoreToVisual(score)

      expect(visual.evaluated).toBe(true)
      expect(visual.score).toBe(score)
      expect(visual.intensity).toBeCloseTo(score / 10, 6)
      expect(visual.hue).toBeCloseTo((score / 10) * 60, 6)
      expect(visual.hue).toBeGreaterThanOrEqual(0)
      expect(visual.hue).toBeLessThanOrEqual(60)
      expect(visual.intensity).toBeGreaterThanOrEqual(0)
      expect(visual.intensity).toBeLessThanOrEqual(1)
    })
  }

  it("anchors the ends of the ramp: 0 is dark red, 10 is bright yellow", () => {
    expect(scoreToVisual(0)).toMatchObject({ intensity: 0, hue: 0 })
    expect(scoreToVisual(10)).toMatchObject({ intensity: 1, hue: 60 })
    expect(scoreToVisual(0).color).toBe("hsl(0 100% 50%)")
    expect(scoreToVisual(10).color).toBe("hsl(60 100% 50%)")
  })

  const FRACTIONAL_SCORES: ReadonlyArray<readonly [number, number, number]> = [
    [0.5, 0.05, 3],
    [2.5, 0.25, 15],
    [5.5, 0.55, 33],
    [9.5, 0.95, 57],
  ]

  for (const [score, intensity, hue] of FRACTIONAL_SCORES) {
    it(`maps fractional score ${score} to midpoint intensity ${intensity} and hue ${hue}`, () => {
      expect(scoreToVisual(score)).toMatchObject({
        evaluated: true,
        score,
        intensity,
        hue,
      })
    })
  }

  it("rises monotonically without jumps between fractional steps", () => {
    const steps = Array.from({ length: 41 }, (_, index) => scoreToVisual(index / 4))

    for (let index = 1; index < steps.length; index += 1) {
      const previous = steps[index - 1]
      const current = steps[index]

      expect(current.intensity).toBeGreaterThanOrEqual(previous.intensity)
      expect(current.hue).toBeGreaterThanOrEqual(previous.hue)
      // A quarter point must move the ramp by exactly a quarter of one point.
      expect(current.intensity - previous.intensity).toBeCloseTo(0.025, 6)
      expect(current.hue - previous.hue).toBeCloseTo(1.5, 6)
    }
  })

  it("names the score bands used by the legend", () => {
    const expected: ReadonlyArray<readonly [number, string]> = [
      [0, "偏弱"],
      [1.9, "偏弱"],
      [2, "待加强"],
      [3.9, "待加强"],
      [4, "中等"],
      [5.9, "中等"],
      [6, "良好"],
      [7.9, "良好"],
      [8, "优秀"],
      [10, "优秀"],
    ]

    for (const [score, level] of expected) {
      expect(scoreToVisual(score).level).toBe(level)
    }
  })
})

describe("scoreToVisual — dirty input robustness", () => {
  const CLAMPED_INPUTS: ReadonlyArray<readonly [string, unknown, number]> = [
    ["negative number", -3, 0],
    ["number above ten", 11, 10],
    ["huge number", 1e6, 10],
    ["tiny negative number", -1e6, 0],
    ["numeric string", "7", 7],
    ["padded numeric string", " 7.5 ", 7.5],
  ]

  for (const [label, raw, expected] of CLAMPED_INPUTS) {
    it(`clamps ${label} into the legal score range`, () => {
      expect(clampScore(raw)).toBe(expected)
      const visual = scoreToVisual(raw)
      expect(visual).toMatchObject({ evaluated: true, score: expected })
      expect(visual.intensity).toBeGreaterThanOrEqual(0)
      expect(visual.hue).toBeGreaterThanOrEqual(0)
      expect(visual.hue).toBeLessThanOrEqual(60)
    })
  }

  const IGNORED_INPUTS: ReadonlyArray<readonly [string, unknown]> = [
    ["NaN", Number.NaN],
    ["positive Infinity", Number.POSITIVE_INFINITY],
    ["negative Infinity", Number.NEGATIVE_INFINITY],
    ["non-numeric string", "seven"],
    ["empty string", ""],
    ["whitespace string", "   "],
    ["null", null],
    ["undefined", undefined],
    ["object", { value: 7 }],
    ["array", [7]],
    ["boolean", true],
  ]

  for (const [label, raw] of IGNORED_INPUTS) {
    it(`ignores ${label} without throwing or emitting a fake glow`, () => {
      expect(clampScore(raw)).toBeNull()

      const visual = scoreToVisual(raw)
      expect(visual.evaluated).toBe(false)
      expect(visual.score).toBeNull()
      expect(visual.intensity).toBe(NEUTRAL_INTENSITY)
      expect(visual.hue).toBe(0)
      expect(visual.color).toBe(NEUTRAL_COLOR)

      const region = buildHeatmapScene({ chest: raw }).byRegion.chest
      expect(region.evaluated).toBe(false)
      expect(region.intensity).toBeGreaterThanOrEqual(0)
      expect(region.hue).toBeGreaterThanOrEqual(0)
      expect(region.hue).toBeLessThanOrEqual(60)
    })
  }

  it("never throws for a whole record that is not an object", () => {
    const inputs: unknown[] = [null, undefined, 42, "not a record", [], true]

    for (const input of inputs) {
      const scene = buildHeatmapScene(input)
      expect(scene.hasScores).toBe(false)
      expect(scene.visuals).toHaveLength(MUSCLE_REGIONS.length)
      expect(scene.visuals.every((visual) => !visual.evaluated)).toBe(true)
    }
  })

  it("survives a hostile getter on the scores record", () => {
    const hostile: Record<string, unknown> = {}
    Object.defineProperty(hostile, "chest", {
      enumerable: true,
      get() {
        throw new Error("boom")
      },
    })

    expect(() => buildHeatmapScene(hostile)).not.toThrow()
    expect(buildHeatmapScene(hostile).hasScores).toBe(false)
  })

  it("survives a record whose key enumeration throws", () => {
    const hostile = new Proxy<Record<string, unknown>>(
      {},
      {
        ownKeys() {
          throw new Error("no keys for you")
        },
      },
    )

    expect(() => buildHeatmapScene(hostile)).not.toThrow()
    expect(buildHeatmapScene(hostile).hasScores).toBe(false)
  })

  it("is deterministic for the same input", () => {
    expect(buildHeatmapScene({ chest: 7, 核心: 4 })).toEqual(
      buildHeatmapScene({ chest: 7, 核心: 4 }),
    )
  })
})

describe("buildHeatmapScene — alias normalisation", () => {
  it("merges 核心 / 腹 / 侧腹 into abs with their average", () => {
    const merged = buildHeatmapScene({ 核心: 4, 腹: 6, 侧腹: 8 }).byRegion.abs
    const direct = buildHeatmapScene({ abs: 6 }).byRegion.abs

    expect(merged.evaluated).toBe(true)
    expect(merged.score).toBe(6)
    expect(merged.intensity).toBeCloseTo(0.6, 6)
    expect(merged.hue).toBeCloseTo(36, 6)
    expect(merged).toMatchObject({
      region: "abs",
      label: direct.label,
      intensity: direct.intensity,
      hue: direct.hue,
      level: direct.level,
    })
    expect(merged.sourceKeys).toEqual(["核心", "腹", "侧腹"])
  })

  it("excludes ignored aliases from the average instead of treating them as 0", () => {
    const scene = buildHeatmapScene({ abs: 4, 核心: 4, 腹: null, 腹部: Number.NaN })

    expect(scene.byRegion.abs.score).toBe(4)
    expect(scene.byRegion.abs.score).not.toBeCloseTo((4 + 4 + 0 + 0) / 4, 6)
  })

  it("accepts english and chinese aliases for the same region", () => {
    expect(scoreOf({ core: 6 }, "abs")).toBe(6)
    expect(scoreOf({ abdomen: 6 }, "abs")).toBe(6)
    expect(scoreOf({ obliques: 6 }, "abs")).toBe(6)
    expect(scoreOf({ 背阔肌: 6 }, "upper_back")).toBe(6)
    expect(scoreOf({ 三角肌: 6 }, "shoulders")).toBe(6)
    expect(scoreOf({ 肱二头: 6 }, "arms")).toBe(6)
    expect(scoreOf({ 股四头: 6 }, "quads")).toBe(6)
    expect(scoreOf({ 腘绳肌: 6 }, "hamstrings")).toBe(6)
  })
})

describe("buildHeatmapScene — left/right pairs", () => {
  it("averages english side keys and reports 单侧偏差 when the gap is at least 3", () => {
    const scene = buildHeatmapScene({ chest_left: 8, chest_right: 4 })
    const chest = scene.byRegion.chest

    expect(chest.score).toBe(6)
    expect(chest.leftScore).toBe(8)
    expect(chest.rightScore).toBe(4)
    expect(scene.annotations).toHaveLength(1)
    expect(scene.annotations[0]).toMatchObject({
      region: "chest",
      kind: "asymmetry",
      title: "单侧偏差",
      left: 8,
      right: 4,
      delta: 4,
    })
    expect(scene.annotations[0].detail).toContain("单侧偏差")
  })

  it("averages chinese side forms", () => {
    const scene = buildHeatmapScene({ 左肩: 9, 右肩: 5 })

    expect(scene.byRegion.shoulders.score).toBe(7)
    expect(scene.annotations[0]).toMatchObject({
      region: "shoulders",
      title: "单侧偏差",
      delta: 4,
    })
  })

  it("merges aliases before averaging each side", () => {
    const scene = buildHeatmapScene({ 左三角肌: 8, 右三角肌: 5 })

    expect(scene.byRegion.shoulders.score).toBe(6.5)
    expect(scene.annotations[0]).toMatchObject({
      region: "shoulders",
      left: 8,
      right: 5,
      delta: 3,
    })
  })

  it("averages every source key when unsided and sided aliases share a region", () => {
    const scene = buildHeatmapScene({ 腹: 2, 侧腹: 4, 左腹: 10, 右腹: 10 })

    // (2 + 4 + 10 + 10) / 4；先按侧求均值再平均会得到 7.67，与「取算术平均」不符。
    expect(scene.byRegion.abs.score).toBe(6.5)
  })

  it(`only flags 单侧偏差 at a gap of ${ASYMMETRY_THRESHOLD} or more`, () => {
    expect(buildHeatmapScene({ chest_left: 6, chest_right: 4 }).annotations).toHaveLength(0)
    expect(buildHeatmapScene({ chest_left: 7, chest_right: 4 }).annotations).toHaveLength(1)
    expect(buildHeatmapScene({ chest_left: 4, chest_right: 7 }).annotations[0].delta).toBe(3)
  })

  it("uses a single evaluated side without inventing a bias", () => {
    const scene = buildHeatmapScene({ shoulders_left: 6 })

    expect(scene.byRegion.shoulders.score).toBe(6)
    expect(scene.byRegion.shoulders.rightScore).toBeNull()
    expect(scene.annotations).toHaveLength(0)
  })
})

describe("buildHeatmapScene — unmergeable keys", () => {
  it("keeps head / neck / legs out of the 3D parameter set but in the list data", () => {
    const scene = buildHeatmapScene({ head: 7, neck: 5, 腿部: 4 })

    expect(scene.visuals).toHaveLength(MUSCLE_REGIONS.length)
    expect(scene.visuals.every((visual) => visual.region !== ("head" as MuscleRegion))).toBe(true)
    expect(scene.byRegion).not.toHaveProperty("head")
    expect(scene.unmapped).toEqual([
      { key: "head", label: "头部", score: 7 },
      { key: "neck", label: "颈部", score: 5 },
      { key: "腿部", label: "腿部", score: 4 },
    ])
    expect(scene.hasScores).toBe(false)
  })

  it("keeps an unknown key with its raw name and never lets it glow", () => {
    const scene = buildHeatmapScene({ mystery_muscle: 9 })

    expect(scene.unmapped).toEqual([
      { key: "mystery_muscle", label: "mystery_muscle", score: 9 },
    ])
    expect(scene.hasScores).toBe(false)
  })

  it("does not mistake object prototype names for muscle regions", () => {
    const scores: Record<string, unknown> = { constructor: 7, toString: 5, hasOwnProperty: 3 }
    Object.defineProperty(scores, "__proto__", {
      value: 6,
      enumerable: true,
      configurable: true,
      writable: true,
    })

    const scene = buildHeatmapScene(scores)

    expect(scene.unmapped.map((entry) => entry.key)).toEqual([
      "constructor",
      "toString",
      "hasOwnProperty",
      "__proto__",
    ])
    expect(scene.unmapped.map((entry) => entry.label)).toEqual([
      "constructor",
      "toString",
      "hasOwnProperty",
      "__proto__",
    ])
    expect(scene.hasScores).toBe(false)
  })

  it("does not lose the label of an unmergeable key with an invalid score", () => {
    const scene = buildHeatmapScene({ head: "not a score" })

    expect(scene.unmapped).toEqual([{ key: "head", label: "头部", score: null }])
  })
})

describe("buildHeatmapScene — unevaluated semantics", () => {
  it("labels a missing region 未评估 without pretending it is a 0", () => {
    const scene = buildHeatmapScene({ chest: 8 })
    const abs = scene.byRegion.abs
    const zero = scoreToVisual(0)

    // The explicit anti-test: a missing region must not become score 0.
    expect(abs.evaluated).toBe(false)
    expect(abs.score).toBeNull()
    expect(abs.score).not.toBe(0)
    expect(abs.intensity).toBe(NEUTRAL_INTENSITY)
    expect(abs.intensity).not.toBe(0)
    expect(abs.intensity).not.toBe(zero.intensity)
    expect(abs.color).toBe(NEUTRAL_COLOR)
    expect(abs.color).not.toBe(zero.color)
    expect(abs.level).toBe("未评估")
    expect(abs.level).not.toBe(zero.level)

    expect(scene.unevaluated).toContain("abs")
    expect(scene.evaluated).toEqual(["chest"])
    expect(scene.legend).toContainEqual(
      expect.objectContaining({
        key: "unevaluated",
        label: "未评估",
        evaluated: false,
        score: null,
        color: NEUTRAL_COLOR,
      }),
    )
  })

  it("keeps missing regions out of every average", () => {
    // If missing were coerced to 0 this would settle around 2.67 instead of 8.
    expect(scoreOf({ 核心: 8 }, "abs")).toBe(8)
    expect(scoreOf({ abs: 8, 腹: null, 侧腹: undefined }, "abs")).toBe(8)
  })

  it("does not leak an unevaluated region into the diff", () => {
    const diff = compareHeatmaps({ chest: 5 }, { chest: 5, abs: 9 })

    expect(diff.changes.map((change) => change.region)).toEqual(["chest"])
    expect(diff.changes[0].delta).toBe(0)
  })

  it("builds a complete legend with a single 未评估 summary item when needed", () => {
    const partial = buildHeatmapScene({ chest: 7 })
    const complete = buildHeatmapScene(FULL_SCORES)

    expect(partial.legend).toHaveLength(MUSCLE_REGIONS.length + 1)
    expect(partial.legend.at(-1)).toMatchObject({ key: "unevaluated", label: "未评估" })
    expect(complete.legend).toHaveLength(MUSCLE_REGIONS.length)
    expect(complete.legend.some((item) => item.key === "unevaluated")).toBe(false)
    expect(HEATMAP_LEGEND_HINT).toBe("发光越亮 = 评分越高")
  })

  it("uses grey for unevaluated legend entries and the score colour for evaluated ones", () => {
    const scene = buildHeatmapScene({ chest: 5 })
    const chest = scene.legend.find((item) => item.key === "chest")
    const abs = scene.legend.find((item) => item.key === "abs")

    expect(chest).toMatchObject({ evaluated: true, score: 5, level: "中等" })
    expect(abs).toMatchObject({ evaluated: false, score: null, color: NEUTRAL_COLOR })
  })

  it("distinguishes an empty record from a body where every region scored 0", () => {
    const empty = buildHeatmapScene({})
    const allZero = buildHeatmapScene(
      Object.fromEntries(MUSCLE_REGIONS.map((region) => [region, 0])),
    )

    expect(empty.hasScores).toBe(false)
    expect(empty.visuals.every((visual) => !visual.evaluated)).toBe(true)
    expect(allZero.hasScores).toBe(true)
    expect(allZero.visuals.every((visual) => visual.evaluated && visual.intensity === 0)).toBe(
      true,
    )
    expect(empty.visuals[0].color).not.toBe(allZero.visuals[0].color)
  })
})

describe("buildHeatmapScene — labels", () => {
  it("defaults to Chinese labels per the page copy", () => {
    expect(buildHeatmapScene({ abs: 6 }).byRegion.abs.label).toBe("腹肌")
    expect(buildHeatmapScene({ chest: 6 }).byRegion.chest.label).toBe("胸部")
  })

  it("accepts an optional label map for regions and unmergeable keys", () => {
    const scene = buildHeatmapScene(
      { chest: 6, head: 5 },
      { labels: { chest: "Chest", head: "Head" } },
    )

    expect(scene.byRegion.chest.label).toBe("Chest")
    expect(scene.legend.find((item) => item.key === "chest")?.label).toBe("Chest")
    expect(scene.unmapped[0]).toMatchObject({ key: "head", label: "Head", score: 5 })
  })
})

describe("compareHeatmaps — change badges", () => {
  it(`only badges a change of ${DIFF_BADGE_THRESHOLD} points or more`, () => {
    expect(compareHeatmaps({ chest: 5 }, { chest: 6 }).badges).toHaveLength(0)

    const up = compareHeatmaps({ chest: 5 }, { chest: 7 })
    expect(up.badges).toHaveLength(1)
    expect(up.changes[0]).toMatchObject({
      region: "chest",
      label: "胸部",
      before: 5,
      after: 7,
      delta: 2,
      direction: "up",
      badge: true,
      badgeLabel: "胸部 +2",
    })

    const down = compareHeatmaps({ chest: 7 }, { chest: 5 })
    expect(down.changes[0]).toMatchObject({
      delta: -2,
      direction: "down",
      badge: true,
      badgeLabel: "胸部 -2",
    })
  })

  it("uses a flat, badge-less change for an unchanged region", () => {
    const diff = compareHeatmaps({ abs: 4 }, { abs: 4 })

    expect(diff.changes[0]).toMatchObject({ delta: 0, direction: "flat", badge: false })
    expect(diff.changes[0].badgeLabel).toBeNull()
    expect(diff.badges).toHaveLength(0)
    expect(diff.topChanges).toHaveLength(0)
  })

  it("produces no badge when either side is unevaluated", () => {
    expect(compareHeatmaps({}, { chest: 9 }).badges).toHaveLength(0)
    expect(compareHeatmaps({ chest: 9 }, {}).badges).toHaveLength(0)
    expect(compareHeatmaps({}, {}).changes).toHaveLength(0)
  })

  it("compares aliased and side-averaged scores by canonical region", () => {
    const aliased = compareHeatmaps({ 核心: 4 }, { abs: 7 })
    expect(aliased.changes[0]).toMatchObject({ region: "abs", delta: 3, badge: true })

    const paired = compareHeatmaps({ chest_left: 4, chest_right: 6 }, { chest: 8 })
    expect(paired.changes[0]).toMatchObject({ region: "chest", before: 5, delta: 3 })
  })

  it("returns the top-N changes by absolute delta with a region-key tiebreak", () => {
    const diff = compareHeatmaps(
      FULL_SCORES,
      { ...FULL_SCORES, calves: 10, chest: 9, upper_back: 8, abs: 7, quads: 6 },
    )

    expect(diff.topN).toBe(DEFAULT_TOP_CHANGES)
    expect(diff.topChanges.map((change) => change.region)).toEqual([
      "calves",
      "chest",
      "upper_back",
    ])
    expect(diff.topChanges.map((change) => change.delta)).toEqual([5, 4, 3])

    const ties = compareHeatmaps(FULL_SCORES, { ...FULL_SCORES, traps: 7, chest: 7, abs: 7 })
    expect(ties.topChanges.map((change) => change.region)).toEqual(["abs", "chest", "traps"])
  })

  it("honours a custom top-N and a zero limit", () => {
    expect(
      compareHeatmaps(FULL_SCORES, { ...FULL_SCORES, calves: 10, chest: 9 }, { topN: 1 }).topChanges,
    ).toHaveLength(1)
    expect(
      compareHeatmaps(FULL_SCORES, { ...FULL_SCORES, calves: 10 }, { topN: 0 }).topChanges,
    ).toHaveLength(0)
  })
})

describe("resolveHeatmapFallback — list view + notice degradation", () => {
  it("falls back to the list when the capability probe fails", () => {
    const state = resolveHeatmapFallback({
      capability: "unsupported",
      modelStatus: "ready",
      scores: { chest: 7 },
    })

    expect(state).toMatchObject({
      mode: "list",
      showsScoreList: true,
      renderModel: false,
      scene: null,
      reason: "capability-unavailable",
      canRetry: false,
      tone: "info",
    })
    expect(state?.notice).toContain("不支持 3D")
    expect(state).not.toHaveProperty("visuals")
  })

  it("treats an inconclusive probe as a list fallback too", () => {
    const state = resolveHeatmapFallback({
      capability: "probe-failed",
      scores: { chest: 7 },
    })

    expect(state).toMatchObject({ reason: "capability-unavailable", canRetry: false, scene: null })
    expect(state?.notice).toContain("无法确认")
  })

  it("falls back to a retryable list when the model fails to load", () => {
    const state = resolveHeatmapFallback({ modelStatus: "failed", scores: { chest: 7 } })

    expect(state).toMatchObject({
      mode: "list",
      showsScoreList: true,
      renderModel: false,
      scene: null,
      reason: "model-load-failed",
      canRetry: true,
      tone: "warning",
    })
    expect(state?.notice).toContain("3D 视图暂不可用")
    expect(state?.notice).toContain("重试")
  })

  it("falls back to the list when the record has no usable scores", () => {
    const empty = resolveHeatmapFallback({ scores: {} })
    const dirty = resolveHeatmapFallback({ scores: { chest: null, abs: Number.NaN } })
    const unmappedOnly = resolveHeatmapFallback({ scores: { head: 7 } })

    for (const state of [empty, dirty, unmappedOnly]) {
      expect(state).toMatchObject({
        mode: "list",
        showsScoreList: true,
        renderModel: false,
        scene: null,
        reason: "no-scores",
        canRetry: false,
        tone: "info",
      })
      expect(state?.notice).toContain("没有部位评分")
    }
  })

  it("allows the 3D view when capability and scores are present", () => {
    expect(
      resolveHeatmapFallback({ capability: "supported", modelStatus: "ready", scores: { chest: 7 } }),
    ).toBeNull()
    expect(
      resolveHeatmapFallback({ capability: "supported", modelStatus: "loading", scores: { chest: 7 } }),
    ).toBeNull()
  })

  it("never hands back render input that could pass for a 0-score body", () => {
    const states = [
      resolveHeatmapFallback({ capability: "unsupported" }),
      resolveHeatmapFallback({ modelStatus: "failed" }),
      resolveHeatmapFallback({ scores: {} }),
    ]

    for (const state of states) {
      expect(state).not.toBeNull()
      expect(state?.renderModel).toBe(false)
      expect(state?.scene).toBeNull()
      expect(state?.showsScoreList).toBe(true)
    }
  })
})
