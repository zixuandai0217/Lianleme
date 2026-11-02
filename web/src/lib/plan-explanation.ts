/*
 * 计划页解释卡与训练量摘要（工单 21）。
 *
 * 训练量由周计划本身派生；「为什么这样练」来自工单 20 暴露的解释字段。这里全部是纯函数，
 * 页面只负责展开/收起与渲染，因此缺数据时的三档降级文案可以逐条断言，不会出现空白块。
 */
import type {
  DailyWorkout,
  PlanExplanation,
  TrainingPlan,
} from "@/api/types"

export const DAY_NAMES = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]

const ENGLISH_FOCUS: Record<string, string> = {
  push: "上肢推",
  pull: "上肢拉",
  legs: "腿部",
  lower: "下肢",
  upper: "上肢",
  core: "核心",
  cardio: "有氧",
  full_body: "全身",
  fullbody: "全身",
  recovery: "恢复",
  rest: "恢复",
}

const CHINESE_CATEGORIES: Array<{ category: string; keywords: string[] }> = [
  { category: "上肢推", keywords: ["胸", "推", "肩"] },
  { category: "上肢拉", keywords: ["背", "拉"] },
  { category: "腿部", keywords: ["腿", "臀"] },
  { category: "核心", keywords: ["核心", "腹"] },
  { category: "有氧", keywords: ["有氧", "跑", "骑"] },
  { category: "全身", keywords: ["全身", "综合"] },
]

export interface NormalizedFocus {
  /** 展示用标签：已知值归一成中文，未知值原样保留。 */
  label: string
  /** 聚合用的稳定分类：已知值落在固定集合，未知值归入「其他」。 */
  category: string
}

const UNKNOWN_CATEGORY = "其他"

export function normalizeFocus(focus: string | null | undefined): NormalizedFocus {
  const raw = (focus ?? "").trim()
  if (!raw) return { label: "未标注重点", category: UNKNOWN_CATEGORY }

  const english = ENGLISH_FOCUS[raw.toLowerCase()]
  if (english) {
    return { label: english, category: english === "恢复" ? "恢复" : english }
  }

  for (const rule of CHINESE_CATEGORIES) {
    if (rule.keywords.some((keyword) => raw.includes(keyword))) {
      return { label: raw, category: rule.category }
    }
  }
  return { label: raw, category: UNKNOWN_CATEGORY }
}

export interface FocusCount {
  category: string
  label: string
  count: number
}

export interface HeavyDay {
  day: number
  label: string
  totalSets: number
  totalMinutes: number
}

export interface VolumeSummary {
  trainingDays: number
  restDays: number
  exerciseCount: number
  totalSets: number
  totalMinutes: number
  focusCounts: FocusCount[]
  heaviestDay: HeavyDay | null
  isRecoveryWeek: boolean
}

function dayVolume(workout: DailyWorkout): { totalSets: number; totalMinutes: number } {
  const totalSets = workout.exercises.reduce((sum, exercise) => sum + exercise.sets, 0)
  return { totalSets, totalMinutes: workout.estimated_duration || 0 }
}

/** Derive the weekly training volume from the plan itself (no API, no algorithm change). */
export function summarizeVolume(plan: TrainingPlan | null | undefined): VolumeSummary {
  const days = plan?.weekly_plan ?? []
  const trainingDays = days.filter((day) => !day.is_rest_day && day.exercises.length > 0)
  const restDays = days.length - trainingDays.length

  let totalSets = 0
  let totalMinutes = 0
  let exerciseCount = 0
  let heaviestDay: HeavyDay | null = null
  const focusCounts = new Map<string, FocusCount>()

  for (const day of trainingDays) {
    const volume = dayVolume(day)
    totalSets += volume.totalSets
    totalMinutes += volume.totalMinutes
    exerciseCount += day.exercises.length

    if (
      heaviestDay === null ||
      volume.totalSets > heaviestDay.totalSets ||
      (volume.totalSets === heaviestDay.totalSets && volume.totalMinutes > heaviestDay.totalMinutes)
    ) {
      heaviestDay = {
        day: day.day,
        label: DAY_NAMES[day.day] ?? `第 ${day.day} 天`,
        totalSets: volume.totalSets,
        totalMinutes: volume.totalMinutes,
      }
    }

    // 同一天同一分类只计一次：重点是「这周练到了哪些部位」，不是动作条目数。
    const focus = normalizeFocus(day.focus)
    if (focus.category === "恢复") continue
    const existing = focusCounts.get(focus.category)
    if (existing) {
      existing.count += 1
    } else {
      focusCounts.set(focus.category, {
        category: focus.category,
        // 展示用稳定分类名：同一天「胸」与「push」归一类时不会出现两个标签。
        label: focus.category,
        count: 1,
      })
    }
  }

  return {
    trainingDays: trainingDays.length,
    restDays,
    exerciseCount,
    totalSets,
    totalMinutes,
    focusCounts: [...focusCounts.values()].sort((a, b) => b.count - a.count),
    heaviestDay,
    isRecoveryWeek: trainingDays.length === 0,
  }
}

export interface WeeklyGoal {
  text: string
  source: "generation" | "current" | "weak_muscles" | "balanced"
}

/** AC5：生成时档案目标 > 当前档案目标 > 弱势肌群概括 > 均衡发展。 */
export function deriveWeeklyGoal(
  explanation: PlanExplanation | null | undefined,
  currentProfileGoal?: string | null,
): WeeklyGoal {
  const generated = explanation?.generation?.profile_goal?.trim()
  if (generated) {
    return { text: `本周目标：${generated}`, source: "generation" }
  }

  const current = currentProfileGoal?.trim()
  if (current) {
    return { text: `本周目标：${current}（按当前档案推断）`, source: "current" }
  }

  const weak = explanation?.generation?.weak_muscles?.filter((item) => item.trim().length > 0) ?? []
  if (weak.length > 0) {
    return { text: `本周重点补强：${weak.join("、")}`, source: "weak_muscles" }
  }

  return { text: "本周以均衡发展为主", source: "balanced" }
}

export interface ExplanationCopy {
  goal: string
  source: string
  volume: string
  adjustment: string
}

/** 生成依据（重点来源）：来自哪一次体型分析；没有就明确说没有。 */
export function describeGenerationBasis(explanation: PlanExplanation | null | undefined): string {
  const generation = explanation?.generation
  if (!generation) {
    return "这份计划生成于解释字段上线之前，暂时没有可回看的生成依据。"
  }
  const parts: string[] = []
  if (generation.body_type) parts.push(`体型 ${generation.body_type}`)
  if (generation.body_fat_range) parts.push(`体脂 ${generation.body_fat_range}`)
  const weak = generation.weak_muscles?.filter((item) => item.trim().length > 0) ?? []
  if (weak.length > 0) parts.push(`弱势肌群 ${weak.join("、")}`)
  if (generation.captured_at) {
    parts.push(`分析时间 ${new Date(generation.captured_at).toLocaleDateString("zh-CN")}`)
  }
  if (parts.length === 0) {
    return "这份计划的生成依据不完整，暂时只能看到训练安排本身。"
  }
  return parts.join(" · ")
}

/** AC4：解释缺失 / 无调整 / 保持原强度 三档文案互不混淆。 */
export function describeAdjustment(explanation: PlanExplanation | null | undefined): string {
  if (!explanation) {
    return "这份计划生成于解释字段上线之前，暂时没有可回看的调整说明。"
  }
  const adjustment = explanation.latest_adjustment
  if (!adjustment) {
    return "本周还没有调整记录，计划按初始安排执行。"
  }
  if (adjustment.direction === "keep") {
    return `本周保持原强度：${adjustment.reason}`
  }
  const direction = adjustment.direction === "increase" ? "上调" : "下调"
  return `本周${direction}强度：${adjustment.reason}`
}

export function describeVolume(summary: VolumeSummary): string {
  if (summary.isRecoveryWeek) {
    return "本周为恢复周：0 个训练日 · 0 个动作 · 0 组 · 预计 0 分钟，专注恢复与轻量活动。"
  }
  const heavy = summary.heaviestDay
  const parts = [
    `${summary.trainingDays} 个训练日 · ${summary.restDays} 个休息日`,
    `${summary.exerciseCount} 个动作 · ${summary.totalSets} 组`,
    `预计 ${summary.totalMinutes} 分钟`,
  ]
  if (heavy) {
    parts.push(`最重的一天：${heavy.label}（${heavy.totalSets} 组 / ${heavy.totalMinutes} 分钟）`)
  }
  if (summary.focusCounts.length > 0) {
    parts.push(
      `重点：${summary.focusCounts.map((item) => `${item.label} ${item.count} 次`).join(" · ")}`,
    )
  }
  return parts.join(" · ")
}

/** Copy bundle used by the card; keeps the four blocks non-empty for every input. */
export function buildExplanationCopy(
  explanation: PlanExplanation | null | undefined,
  plan: TrainingPlan | null | undefined,
  currentProfileGoal?: string | null,
): ExplanationCopy {
  const goal = deriveWeeklyGoal(explanation, currentProfileGoal)
  const summary = summarizeVolume(plan)
  return {
    goal: goal.text,
    source: describeGenerationBasis(explanation),
    volume: describeVolume(summary),
    adjustment: describeAdjustment(explanation),
  }
}
