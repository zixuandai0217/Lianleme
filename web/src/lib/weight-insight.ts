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
  tone: InsightTone
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

export interface WeightInsightView {
  visible: boolean
  headline: string
  tone: InsightTone
  staleNotice: string | null
  caption: string | null
  windows: WeightWindowView[]
  singleRecordHint: string | null
  weeklyVisible: boolean
  weeklyTitle: string
  weeklyRows: WeeklyRowView[]
  goalNote: string | null
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
  tone: InsightTone,
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
    tone,
    directionWord,
    changeText,
    rangeText,
    insufficient: window.insufficient,
  }
}

function toneFor(goal: WeightGoalInsight): InsightTone {
  if (goal.mode === "none") return "neutral"
  if (goal.verdict === "on_track") return "positive"
  if (goal.verdict === "off_track") return "warning"
  return "neutral"
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

/** 把接口返回的锚点统计翻译成解读区视图模型；无任何记录时 visible=false。 */
export function buildWeightInsightView(insight: WeightInsights): WeightInsightView {
  const goal = insight.goal ?? { mode: "none", verdict: "neutral" }
  const tone = toneFor(goal)
  const hasAnchor = Boolean(insight.anchor_date)

  if (!hasAnchor) {
    return {
      visible: false,
      headline: "",
      tone,
      staleNotice: null,
      caption: null,
      windows: [],
      singleRecordHint: null,
      weeklyVisible: false,
      weeklyTitle: WEEKLY_TITLE,
      weeklyRows: [],
      goalNote: null,
    }
  }

  const windows: WeightWindowView[] = []
  if (insight.windows?.d7) windows.push(buildWindowView("d7", insight.windows.d7, tone))
  if (insight.windows?.d30) windows.push(buildWindowView("d30", insight.windows.d30, tone))

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
    tone,
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
    goalNote: null,
  }
}
