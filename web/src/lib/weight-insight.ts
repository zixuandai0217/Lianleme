/* 体重趋势解读：把接口的锚点统计翻译成结论句、事实行与分档（纯函数，无副作用）。 */

export type InsightDirection = "down" | "up" | "flat" | "insufficient"
export type WeeklyRelation = "same" | "reverse" | "flat" | "insufficient"
export type InsightTone = "neutral" | "positive" | "warning"

export interface WeightExtreme {
  weight: number
  recorded_date: string
}

export interface WeightInsightWindow {
  days: number
  start_date?: string | null
  end_date?: string | null
  sample_count: number
  change: number | null
  direction: InsightDirection
  min: WeightExtreme | null
  max: WeightExtreme | null
  insufficient: boolean
}

export interface WeightWeeklyComparison {
  week_start: string
  week_end: string
  sample_count: number
  weight_change: number | null
  training_days: number
  relation: WeeklyRelation
}

export interface WeightGoalInsight {
  mode: "numeric" | "direction" | "none"
  verdict: string
  reason?: string
  gap?: number | null
  target_weight?: number | null
  goal_label?: string | null
  expected_direction?: "down" | "up" | "hold" | null
}

export interface WeightInsights {
  anchor_date: string | null
  is_stale: boolean
  stale_days: number
  windows: { d7: WeightInsightWindow; d30: WeightInsightWindow }
  weekly: WeightWeeklyComparison[]
  training_data_available: boolean
  goal: WeightGoalInsight
}

export interface WeightWindowView {
  key: "d7" | "d30"
  label: string
  directionWord: string
  changeText: string | null
  rangeText: string | null
  insufficient: boolean
}

export interface WeeklyRowView {
  key: string
  label: string
  factText: string
}

/** 目标判定块：颜色只由目标结论决定，窗口卡保持中性，避免给 7 天窗口套用 30 天结论 */
export interface WeightGoalView {
  tone: InsightTone
  headline: string
  note: string | null
}

export interface WeightInsightView {
  visible: boolean
  headline: string
  staleNotice: string | null
  caption: string | null
  windows: WeightWindowView[]
  singleRecordHint: string | null
  weeklyVisible: boolean
  weeklyTitle: string
  weeklyRows: WeeklyRowView[]
  goal: WeightGoalView | null
}

const DIRECTION_WORDS: Record<InsightDirection, string> = {
  down: "下降",
  up: "上升",
  flat: "持平",
  insufficient: "数据不足",
}

const RELATION_WORDS: Record<WeeklyRelation, string> = {
  same: "同向",
  reverse: "反向",
  flat: "无明显关系",
  insufficient: "数据不足",
}

const WEEKLY_TITLE = "最近 4 周：体重变化与训练天数"

/** 目标结论 -> 颜色与结论句；未知取值不渲染目标块（旧响应/未来新码都不崩） */
const VERDICT_META: Record<string, { tone: InsightTone; headline: string }> = {
  on_track: { tone: "positive", headline: "朝目标前进" },
  off_track: { tone: "warning", headline: "偏离目标" },
  steady: { tone: "neutral", headline: "基本持平" },
  insufficient: { tone: "neutral", headline: "数据不足，暂不判断" },
}

const EXPECTED_WORDS: Record<string, string> = {
  down: "下降",
  up: "上升",
  hold: "维持",
}

function formatDate(isoDate: string): string {
  const [, month, day] = isoDate.split("-")
  return `${Number(month)}月${Number(day)}日`
}

function formatWeight(value: number): string {
  return `${value.toFixed(1)} kg`
}

function formatChange(change: number): string {
  const rounded = Number(change.toFixed(1))
  if (rounded > 0) return `+${rounded.toFixed(1)} kg`
  return `${rounded.toFixed(1)} kg`
}

function buildWindowView(
  key: "d7" | "d30",
  window: WeightInsightWindow,
): WeightWindowView {
  const directionWord = DIRECTION_WORDS[window.direction] ?? DIRECTION_WORDS.insufficient
  const changeText =
    window.insufficient || window.change == null ? null : formatChange(window.change)
  const rangeText =
    window.min && window.max
      ? `最低 ${formatWeight(window.min.weight)}（${formatDate(window.min.recorded_date)}）· `
        + `最高 ${formatWeight(window.max.weight)}（${formatDate(window.max.recorded_date)}）`
      : null

  return {
    key,
    label: `最近 ${window.days} 天`,
    directionWord,
    changeText,
    rangeText,
    insufficient: window.insufficient,
  }
}

function headlineFor(insight: WeightInsights): string {
  const d30 = insight.windows?.d30
  const d7 = insight.windows?.d7
  const picked = d30 && !d30.insufficient ? d30 : d7 && !d7.insufficient ? d7 : null
  if (!picked) return "数据不足，暂不下结论"
  if (picked.direction === "flat") return `最近 ${picked.days} 天基本持平`
  if (picked.direction === "down") return `最近 ${picked.days} 天呈下降趋势`
  if (picked.direction === "up") return `最近 ${picked.days} 天呈上升趋势`
  return "数据不足，暂不下结论"
}

function weeklyRowView(week: WeightWeeklyComparison): WeeklyRowView {
  const label = `${formatDate(week.week_start)}–${formatDate(week.week_end)}`
  const trainingFact = `同期训练 ${week.training_days} 天`
  const relationFact = `与近 30 天${RELATION_WORDS[week.relation] ?? RELATION_WORDS.insufficient}`
  const weightFact =
    week.weight_change == null || week.sample_count < 2
      ? "体重变化记录不足 2 条"
      : `体重 ${formatChange(week.weight_change)}`

  return {
    key: week.week_start,
    label,
    factText: `${weightFact}，${trainingFact}（${relationFact}）`,
  }
}

function changeFact(window: WeightInsightWindow | undefined): string {
  if (!window || window.insufficient || window.change == null) return "最近 30 天数据不足"
  const directionWord = DIRECTION_WORDS[window.direction] ?? DIRECTION_WORDS.insufficient
  return `最近 30 天${directionWord} ${Math.abs(window.change).toFixed(1)} kg`
}

function goalNoteFor(goal: WeightGoalInsight, insight: WeightInsights): string {
  const recent = changeFact(insight.windows?.d30)
  if (goal.mode === "direction") {
    const expected = EXPECTED_WORDS[goal.expected_direction ?? "hold"] ?? EXPECTED_WORDS.hold
    return `${goal.goal_label ?? "当前目标"}期望${expected} · ${recent}`
  }
  if (goal.reason === "target_reached" && goal.target_weight != null) {
    return `已到目标体重（目标 ${goal.target_weight.toFixed(1)} kg） · ${recent}`
  }
  if (goal.gap == null) {
    return goal.target_weight != null
      ? `目标 ${goal.target_weight.toFixed(1)} kg · ${recent}`
      : recent
  }
  // 目标可能高于或低于当前体重，因此同时给出差距与目标值，避免只写"距目标"引起方向误读
  const target =
    goal.target_weight != null ? `（目标 ${goal.target_weight.toFixed(1)} kg）` : ""
  return `距目标 ${Math.abs(goal.gap).toFixed(1)} kg${target} · ${recent}`
}

function buildGoalView(
  goal: WeightGoalInsight,
  insight: WeightInsights,
): WeightGoalView | null {
  if (goal.mode === "none") return null
  const meta = VERDICT_META[goal.verdict]
  if (!meta) return null
  if (goal.reason === "target_reached") {
    return { tone: meta.tone, headline: "已达目标体重", note: goalNoteFor(goal, insight) }
  }
  // 按方向推断的结论必须在结论句里标明来源，读屏与速读都不依赖事实行
  const headline = goal.mode === "direction" ? `${meta.headline}（按目标方向推断）` : meta.headline
  return { tone: meta.tone, headline, note: goalNoteFor(goal, insight) }
}

/** 把接口返回的锚点统计翻译成解读区视图模型；无任何记录时 visible=false。 */
export function buildWeightInsightView(insight: WeightInsights): WeightInsightView {
  const goal: WeightGoalInsight = insight.goal ?? { mode: "none", verdict: "neutral" }
  const hasAnchor = Boolean(insight.anchor_date)

  if (!hasAnchor) {
    return {
      visible: false,
      headline: "",
      staleNotice: null,
      caption: null,
      windows: [],
      singleRecordHint: null,
      weeklyVisible: false,
      weeklyTitle: WEEKLY_TITLE,
      weeklyRows: [],
      goal: null,
    }
  }

  const goalView = buildGoalView(goal, insight)
  const windows: WeightWindowView[] = []
  if (insight.windows?.d7) windows.push(buildWindowView("d7", insight.windows.d7))
  if (insight.windows?.d30) windows.push(buildWindowView("d30", insight.windows.d30))

  const maxSamples = Math.max(
    insight.windows?.d7?.sample_count ?? 0,
    insight.windows?.d30?.sample_count ?? 0,
  )
  const singleRecordHint =
    maxSamples <= 1 ? "已记录 1 次，再记一次就能看出方向" : null
  const weeklyRows = (insight.weekly ?? []).map(weeklyRowView)

  return {
    visible: true,
    headline: singleRecordHint ? "数据不足，暂不下结论" : headlineFor(insight),
    staleNotice: insight.is_stale
      ? `距上次记录已 ${insight.stale_days} 天，建议补记一次体重`
      : null,
    caption:
      insight.is_stale && insight.anchor_date
        ? `基于最近一次记录（${formatDate(insight.anchor_date)}）`
        : null,
    windows,
    singleRecordHint,
    weeklyVisible: insight.training_data_available && weeklyRows.length > 0,
    weeklyTitle: WEEKLY_TITLE,
    weeklyRows,
    goal: goalView,
  }
}
