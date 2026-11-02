/* Pure score → visual mapping for the 3D muscle heatmap.
 *
 * This module is the only contract between the vision scores and the renderer:
 * no DOM, no Three.js, no clocks, no randomness. Ticket 45 consumes
 * `buildHeatmapScene` / `compareHeatmaps` / `resolveHeatmapFallback` and only
 * pastes the returned numbers onto materials.
 */

export const MUSCLE_REGIONS = [
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
] as const

/** The GLB mesh names are the single source of truth (ADR-0005 + feature spec). */
export type MuscleRegion = (typeof MUSCLE_REGIONS)[number]

export const MUSCLE_REGION_LABELS: Readonly<Record<MuscleRegion, string>> = {
  chest: "胸部",
  upper_back: "上背",
  lower_back: "下背",
  abs: "腹肌",
  traps: "斜方肌",
  shoulders: "肩部",
  arms: "手臂",
  forearms: "前臂",
  glutes: "臀部",
  quads: "大腿前侧",
  hamstrings: "大腿后侧",
  calves: "小腿",
}

export const SCORE_MIN = 0
export const SCORE_MAX = 10
export const HUE_MIN = 0
export const HUE_MAX = 60
/** A missing region gets a barely-there neutral glow, never a 0-score one. */
export const NEUTRAL_INTENSITY = 0.04
export const NEUTRAL_HUE = 0
export const NEUTRAL_COLOR = "hsl(0 0% 55%)"

export const ASYMMETRY_THRESHOLD = 3
export const DIFF_BADGE_THRESHOLD = 2
export const DEFAULT_TOP_CHANGES = 3
export const HEATMAP_LEGEND_HINT = "发光越亮 = 评分越高"

export type MuscleLevel = "偏弱" | "待加强" | "中等" | "良好" | "优秀" | "未评估"

export interface ScoreVisual {
  evaluated: boolean
  score: number | null
  intensity: number
  hue: number
  color: string
  level: MuscleLevel
}

export interface MuscleVisual extends ScoreVisual {
  region: MuscleRegion
  label: string
  sourceKeys: string[]
  leftScore: number | null
  rightScore: number | null
}

export interface UnmappedMuscleScore {
  key: string
  label: string
  score: number | null
}

export interface HeatmapAnnotation {
  region: MuscleRegion
  regionLabel: string
  kind: "asymmetry"
  title: "单侧偏差"
  left: number
  right: number
  delta: number
  detail: string
}

export interface HeatmapLegendItem {
  key: MuscleRegion | "unevaluated"
  label: string
  color: string
  intensity: number
  evaluated: boolean
  level: MuscleLevel
  score: number | null
}

export interface HeatmapScene {
  visuals: MuscleVisual[]
  byRegion: Record<MuscleRegion, MuscleVisual>
  legend: HeatmapLegendItem[]
  evaluated: MuscleRegion[]
  unevaluated: MuscleRegion[]
  unmapped: UnmappedMuscleScore[]
  annotations: HeatmapAnnotation[]
  hasScores: boolean
}

export type HeatmapLabelMap = Readonly<Record<string, string>>

export interface HeatmapOptions {
  /**
   * Optional locale overrides: canonical region keys rename a muscle every time,
   * while source keys rename an unmapped entry in the list view.
   */
  labels?: HeatmapLabelMap
}

export interface HeatmapChange {
  region: MuscleRegion
  label: string
  before: number
  after: number
  delta: number
  direction: "up" | "down" | "flat"
  badge: boolean
  badgeLabel: string | null
}

export interface HeatmapDiff {
  changes: HeatmapChange[]
  badges: HeatmapChange[]
  topChanges: HeatmapChange[]
  topN: number
}

export type HeatmapFallbackReason = "capability-unavailable" | "model-load-failed" | "no-scores"
export type HeatmapCapability = "supported" | "unsupported" | "probe-failed"
export type HeatmapModelStatus = "idle" | "loading" | "ready" | "failed"

/** "list view + notice": the page renders the score list and never mounts a model. */
export interface HeatmapFallbackState {
  readonly mode: "list"
  readonly showsScoreList: true
  readonly renderModel: false
  readonly scene: null
  readonly reason: HeatmapFallbackReason
  readonly notice: string
  readonly canRetry: boolean
  readonly tone: "info" | "warning"
}

export interface ResolveHeatmapFallbackInput {
  capability?: HeatmapCapability
  modelStatus?: HeatmapModelStatus
  scores?: unknown
}

type MuscleSide = "left" | "right"

const REGION_ALIASES: Readonly<Record<MuscleRegion, readonly string[]>> = {
  chest: [
    "chest",
    "pecs",
    "pec",
    "pectoral",
    "pectorals",
    "pectoralis",
    "pectoralis_major",
    "胸",
    "胸部",
    "胸肌",
    "前胸",
    "上胸",
  ],
  upper_back: [
    "upper_back",
    "back",
    "背",
    "背部",
    "上背",
    "背阔",
    "背阔肌",
    "lats",
    "lat",
    "latissimus",
    "latissimus_dorsi",
  ],
  lower_back: [
    "lower_back",
    "lowerback",
    "下背",
    "腰",
    "腰部",
    "下腰",
    "腰椎",
    "waist",
    "lumbar",
  ],
  abs: [
    "abs",
    "ab",
    "abdomen",
    "abdominal",
    "abdominals",
    "core",
    "obliques",
    "oblique",
    "腹",
    "腹部",
    "腹肌",
    "侧腹",
    "侧腹部",
    "核心",
    "腰腹",
    "中段",
  ],
  traps: ["traps", "trap", "trapezius", "斜方", "斜方肌"],
  shoulders: ["shoulders", "shoulder", "delts", "delt", "deltoid", "deltoids", "肩", "肩部", "三角", "三角肌"],
  arms: [
    "arms",
    "arm",
    "upper_arm",
    "upper_arms",
    "biceps",
    "bicep",
    "triceps",
    "tricep",
    "肱二头",
    "肱二头肌",
    "肱三头",
    "肱三头肌",
    "上臂",
    "大臂",
    "臂",
    "手臂",
  ],
  forearms: ["forearms", "forearm", "lower_arm", "前臂", "小臂", "前臂肌"],
  glutes: [
    "glutes",
    "glute",
    "gluteus",
    "gluteus_maximus",
    "gluteal",
    "臀",
    "臀部",
    "臀肌",
    "屁股",
    "髋",
    "髋部",
    "hips",
    "hip",
  ],
  quads: [
    "quads",
    "quad",
    "quadriceps",
    "quadricep",
    "quadriceps_femoris",
    "thigh_front",
    "front_thigh",
    "股四头",
    "股四头肌",
    "大腿前",
    "大腿前侧",
    "前大腿",
  ],
  hamstrings: [
    "hamstrings",
    "hamstring",
    "hams",
    "biceps_femoris",
    "thigh_back",
    "back_thigh",
    "腘绳",
    "腘绳肌",
    "大腿后",
    "大腿后侧",
    "后大腿",
  ],
  calves: [
    "calves",
    "calf",
    "lower_leg",
    "gastrocnemius",
    "soleus",
    "小腿",
    "小腿肚",
    "小腿肌",
    "腓肠肌",
  ],
}

const UNMAPPED_LABELS: Readonly<Record<string, string>> = {
  head: "头部",
  头: "头部",
  头部: "头部",
  neck: "颈部",
  颈: "颈部",
  颈部: "颈部",
  脖子: "颈部",
  legs: "腿部",
  leg: "腿部",
  腿: "腿部",
  腿部: "腿部",
  下肢: "腿部",
  thigh: "大腿",
  大腿: "大腿",
  torso: "躯干",
  躯干: "躯干",
  full_body: "全身",
  fullbody: "全身",
  全身: "全身",
}

function normalizeKey(key: string): string {
  return key
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
}

/** Built once: every canonical key, its Chinese label, and every alias. */
export const MUSCLE_REGION_ALIASES: Readonly<Record<string, MuscleRegion>> = (() => {
  const aliases: Record<string, MuscleRegion> = {}
  for (const region of MUSCLE_REGIONS) {
    aliases[normalizeKey(region)] = region
    aliases[normalizeKey(MUSCLE_REGION_LABELS[region])] = region
    for (const alias of REGION_ALIASES[region]) {
      aliases[normalizeKey(alias)] = region
    }
  }
  return aliases
})()

function splitSide(normalizedKey: string): { side: MuscleSide | null; base: string } {
  const englishPrefix = /^(left|right)_(.+)$/.exec(normalizedKey)
  if (englishPrefix) {
    return { side: englishPrefix[1] as MuscleSide, base: englishPrefix[2] }
  }

  const englishSuffix = /^(.+)_(left|right)$/.exec(normalizedKey)
  if (englishSuffix) {
    return { side: englishSuffix[2] as MuscleSide, base: englishSuffix[1] }
  }

  const chinesePrefix = /^(左|右)侧?(.+)$/.exec(normalizedKey)
  if (chinesePrefix) {
    return { side: chinesePrefix[1] === "左" ? "left" : "right", base: chinesePrefix[2] }
  }

  const chineseSuffix = /^(.+)(左|右)侧?$/.exec(normalizedKey)
  if (chineseSuffix) {
    return { side: chineseSuffix[2] === "左" ? "left" : "right", base: chineseSuffix[1] }
  }

  return { side: null, base: normalizedKey }
}

function resolveRegion(
  normalizedKey: string,
): { region: MuscleRegion | null; base: string; side: MuscleSide | null } {
  const { side, base } = splitSide(normalizedKey)
  const region = Object.hasOwn(MUSCLE_REGION_ALIASES, base) ? MUSCLE_REGION_ALIASES[base] : null
  return { region, base, side }
}

function clampFinite(value: number): number | null {
  if (!Number.isFinite(value)) return null
  return Math.min(SCORE_MAX, Math.max(SCORE_MIN, value))
}

/** Clamp a finite score to 0..10; ignore anything that is not a real number. */
export function clampScore(value: unknown): number | null {
  if (typeof value === "number") return clampFinite(value)
  if (typeof value === "string") {
    const trimmed = value.trim()
    if (trimmed === "") return null
    return clampFinite(Number(trimmed))
  }
  return null
}

function round(value: number, digits = 6): number {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function levelFor(score: number): MuscleLevel {
  if (score < 2) return "偏弱"
  if (score < 4) return "待加强"
  if (score < 6) return "中等"
  if (score < 8) return "良好"
  return "优秀"
}

/** ADR-0005: emissiveIntensity = score / 10, hue = score / 10 * 60. */
export function scoreToVisual(score: unknown): ScoreVisual {
  const clamped = clampScore(score)
  if (clamped === null) {
    return {
      evaluated: false,
      score: null,
      intensity: NEUTRAL_INTENSITY,
      hue: NEUTRAL_HUE,
      color: NEUTRAL_COLOR,
      level: "未评估",
    }
  }

  const intensity = round(clamped / SCORE_MAX)
  const hue = round((clamped / SCORE_MAX) * HUE_MAX)

  return {
    evaluated: true,
    score: clamped,
    intensity,
    hue,
    color: `hsl(${hue} 100% 50%)`,
    level: levelFor(clamped),
  }
}

function mean(values: readonly number[]): number | null {
  if (values.length === 0) return null
  return values.reduce((total, value) => total + value, 0) / values.length
}

function readScoreEntries(scores: unknown): Array<[string, unknown]> {
  if (typeof scores !== "object" || scores === null || Array.isArray(scores)) return []

  const record = scores as Record<string, unknown>
  let keys: string[]
  try {
    keys = Object.keys(record)
  } catch {
    // A hostile proxy must not break the mapping.
    return []
  }

  const entries: Array<[string, unknown]> = []
  for (const key of keys) {
    try {
      entries.push([key, record[key]])
    } catch {
      // Ignore a single unreadable property, keep the rest.
    }
  }
  return entries
}

function ownValue<T>(record: Readonly<Record<string, T>>, key: string): T | null {
  return Object.hasOwn(record, key) ? record[key] : null
}

function labelOverride(labels: HeatmapLabelMap, key: string): string | null {
  const value = ownValue(labels, key)
  return typeof value === "string" && value !== "" ? value : null
}

function resolveRegionLabel(region: MuscleRegion, labels: HeatmapLabelMap): string {
  return labelOverride(labels, region) ?? MUSCLE_REGION_LABELS[region]
}

function resolveUnmappedLabel(
  rawKey: string,
  normalizedKey: string,
  base: string,
  labels: HeatmapLabelMap,
): string {
  return (
    labelOverride(labels, rawKey)
    ?? labelOverride(labels, normalizedKey)
    ?? labelOverride(labels, base)
    ?? ownValue(UNMAPPED_LABELS, normalizedKey)
    ?? ownValue(UNMAPPED_LABELS, base)
    ?? rawKey
  )
}

function formatScore(value: number): string {
  return String(round(value, 1))
}

interface RegionContribution {
  side: MuscleSide | null
  score: number
  key: string
}

/** Normalise any `muscle_scores` dictionary into the 12-region render contract. */
export function buildHeatmapScene(scores: unknown, options: HeatmapOptions = {}): HeatmapScene {
  const labels = options.labels ?? {}
  const contributions = new Map<MuscleRegion, RegionContribution[]>()
  const unmapped: UnmappedMuscleScore[] = []

  for (const [rawKey, rawValue] of readScoreEntries(scores)) {
    const normalizedKey = normalizeKey(rawKey)
    if (normalizedKey === "") continue

    const { region, base, side } = resolveRegion(normalizedKey)
    const parsed = clampScore(rawValue)

    if (region === null) {
      unmapped.push({
        key: rawKey,
        label: resolveUnmappedLabel(rawKey, normalizedKey, base, labels),
        score: parsed,
      })
      continue
    }

    if (parsed === null) continue
    const bucket = contributions.get(region)
    if (bucket) bucket.push({ side, score: parsed, key: rawKey })
    else contributions.set(region, [{ side, score: parsed, key: rawKey }])
  }

  const visuals: MuscleVisual[] = []
  const annotations: HeatmapAnnotation[] = []

  for (const region of MUSCLE_REGIONS) {
    const bucket = contributions.get(region) ?? []
    const leftValues: number[] = []
    const rightValues: number[] = []

    for (const contribution of bucket) {
      if (contribution.side === "left") leftValues.push(contribution.score)
      else if (contribution.side === "right") rightValues.push(contribution.score)
    }

    const leftScore = mean(leftValues)
    const rightScore = mean(rightValues)
    // 区域分是「落到该区域的全部源键」的算术平均；先按侧求均值再平均会让
    // 左侧/右侧各算一票，和「核心/腹/侧腹取平均」的语义不一致。
    const score = mean(bucket.map((contribution) => contribution.score))

    const label = resolveRegionLabel(region, labels)
    visuals.push({
      ...scoreToVisual(score),
      region,
      label,
      sourceKeys: bucket.map((contribution) => contribution.key),
      leftScore,
      rightScore,
    })

    if (leftScore !== null && rightScore !== null) {
      const delta = round(Math.abs(leftScore - rightScore))
      if (delta >= ASYMMETRY_THRESHOLD) {
        annotations.push({
          region,
          regionLabel: label,
          kind: "asymmetry",
          title: "单侧偏差",
          left: leftScore,
          right: rightScore,
          delta,
          detail: `${label} 左侧 ${formatScore(leftScore)} / 右侧 ${formatScore(rightScore)}，单侧偏差 ${formatScore(delta)} 分`,
        })
      }
    }
  }

  const byRegion = {} as Record<MuscleRegion, MuscleVisual>
  for (const visual of visuals) byRegion[visual.region] = visual

  const evaluated = visuals.filter((visual) => visual.evaluated).map((visual) => visual.region)
  const unevaluated = visuals
    .filter((visual) => !visual.evaluated)
    .map((visual) => visual.region)

  const legend: HeatmapLegendItem[] = visuals.map((visual) => ({
    key: visual.region,
    label: visual.label,
    color: visual.color,
    intensity: visual.intensity,
    evaluated: visual.evaluated,
    level: visual.level,
    score: visual.score,
  }))

  if (unevaluated.length > 0) {
    legend.push({
      key: "unevaluated",
      label: "未评估",
      color: NEUTRAL_COLOR,
      intensity: NEUTRAL_INTENSITY,
      evaluated: false,
      level: "未评估",
      score: null,
    })
  }

  return {
    visuals,
    byRegion,
    legend,
    evaluated,
    unevaluated,
    unmapped,
    annotations,
    hasScores: evaluated.length > 0,
  }
}

function normalizeTopN(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) return DEFAULT_TOP_CHANGES
  return Math.max(0, Math.floor(value))
}

/** Badge only when |Δ| ≥ 2; unevaluated on either side never produces a change. */
export function compareHeatmaps(
  before: unknown,
  after: unknown,
  options: HeatmapOptions & { topN?: number } = {},
): HeatmapDiff {
  const beforeScene = buildHeatmapScene(before, options)
  const afterScene = buildHeatmapScene(after, options)
  const topN = normalizeTopN(options.topN)
  const changes: HeatmapChange[] = []

  for (const region of MUSCLE_REGIONS) {
    const beforeVisual = beforeScene.byRegion[region]
    const afterVisual = afterScene.byRegion[region]
    if (beforeVisual.score === null || afterVisual.score === null) continue

    const delta = round(afterVisual.score - beforeVisual.score)
    const direction: HeatmapChange["direction"] = delta > 0 ? "up" : delta < 0 ? "down" : "flat"
    const badge = Math.abs(delta) >= DIFF_BADGE_THRESHOLD

    changes.push({
      region,
      label: afterVisual.label,
      before: beforeVisual.score,
      after: afterVisual.score,
      delta,
      direction,
      badge,
      badgeLabel: badge ? `${afterVisual.label} ${delta > 0 ? "+" : ""}${formatScore(delta)}` : null,
    })
  }

  const topChanges = changes
    .filter((change) => change.delta !== 0)
    .sort(
      (left, right) =>
        Math.abs(right.delta) - Math.abs(left.delta)
        || (left.region < right.region ? -1 : left.region > right.region ? 1 : 0),
    )
    .slice(0, topN)

  return {
    changes,
    badges: changes.filter((change) => change.badge),
    topChanges,
    topN,
  }
}

export function capabilityFailureState(
  capability: HeatmapCapability = "unsupported",
): HeatmapFallbackState {
  return {
    mode: "list",
    showsScoreList: true,
    renderModel: false,
    scene: null,
    reason: "capability-unavailable",
    notice:
      capability === "probe-failed"
        ? "无法确认设备的 3D 能力，已切换为列表视图。"
        : "当前设备不支持 3D 视图，已切换为列表视图。",
    canRetry: false,
    tone: "info",
  }
}

export function modelLoadFailureState(): HeatmapFallbackState {
  return {
    mode: "list",
    showsScoreList: true,
    renderModel: false,
    scene: null,
    reason: "model-load-failed",
    notice: "3D 视图暂不可用，已切换为列表视图，可稍后重试。",
    canRetry: true,
    tone: "warning",
  }
}

export function emptyScoresState(): HeatmapFallbackState {
  return {
    mode: "list",
    showsScoreList: true,
    renderModel: false,
    scene: null,
    reason: "no-scores",
    notice: "这次分析没有部位评分，已切换为列表视图。",
    canRetry: false,
    tone: "info",
  }
}

/** Decide whether the page may mount the 3D view at all; null means yes. */
export function resolveHeatmapFallback(
  input: ResolveHeatmapFallbackInput = {},
): HeatmapFallbackState | null {
  const capability = input.capability ?? "supported"
  if (capability !== "supported") return capabilityFailureState(capability)

  if (!buildHeatmapScene(input.scores).hasScores) return emptyScoresState()

  if ((input.modelStatus ?? "ready") === "failed") return modelLoadFailureState()

  return null
}
