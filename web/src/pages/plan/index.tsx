/* Refined weekly training plan workspace with polished day selector, exercise cards, and empty state. */
import { useEffect, useState } from "react"
import {
  ArrowRight,
  CalendarDays,
  Clock,
  Dumbbell,
  Heart,
  Loader2,
  Sparkles,
  Timer,
  Trophy,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { generatePlan, getCurrentPlan } from "@/api"
import type { DailyWorkout, Exercise, TrainingPlan } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"
import { cn } from "@/lib/utils"

const DAY_NAMES = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
const FOCUS_LABELS: Record<string, string> = {
  push: "上肢推",
  pull: "上肢拉",
  legs: "腿部",
  core: "核心",
  full_body: "全身",
  upper: "上肢",
  lower: "下肢",
  cardio: "有氧",
  recovery: "恢复",
}

function focusLabel(english: string): string {
  return FOCUS_LABELS[english.toLowerCase()] || english
}

// ── Exercise card ────────────────────────────────────────────────

function ExerciseCard({ exercise, index }: { exercise: Exercise; index: number }) {
  return (
    <div className="group grid gap-3 rounded-lg border border-border bg-card px-4 py-4 shadow-[0_2px_8px_rgba(23,26,23,0.03)] transition-shadow hover:shadow-[0_4px_16px_rgba(23,26,23,0.06)] sm:grid-cols-[2.5rem_1fr_auto] sm:items-center">
      {/* Number */}
      <span className="hidden font-heading text-sm font-semibold text-primary/60 sm:block">
        {String(index + 1).padStart(2, "0")}
      </span>

      {/* Info */}
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-body text-sm font-semibold text-foreground sm:text-base">{exercise.name}</span>
          <Badge variant="outline" className="shrink-0 border-primary/20 bg-primary/5 px-1.5 py-0 text-[0.65rem] text-primary">
            {exercise.weight_suggestion}
          </Badge>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 font-sans text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Dumbbell className="size-3.5 text-muted-foreground/50" />
            {exercise.sets} 组 × {exercise.reps}
          </span>
          <span className="flex items-center gap-1.5">
            <Timer className="size-3.5 text-muted-foreground/50" />
            组间休息 {exercise.rest_seconds} 秒
          </span>
        </div>
        {exercise.tips && (
          <p className="mt-2 flex items-start gap-1.5 border-t border-border/50 pt-2 text-xs leading-5 text-muted-foreground">
            <span className="mt-0.5 shrink-0 text-primary/60">💡</span>
            {exercise.tips}
          </p>
        )}
      </div>

      {/* Sets indicator — subtle visual */}
      <div className="hidden justify-self-end sm:flex sm:items-center sm:gap-1">
        {Array.from({ length: Math.min(exercise.sets, 5) }).map((_, set) => (
          <span
            key={set}
            className="size-2 rounded-full bg-primary/20"
          />
        ))}
      </div>
    </div>
  )
}

// ── Day workout panel ────────────────────────────────────────────

function DayWorkout({ workout }: { workout: DailyWorkout }) {
  if (workout.is_rest_day) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/50 px-6 py-16 text-center">
        <span className="mb-5 flex size-14 items-center justify-center rounded-full bg-brand-green/10 text-brand-green">
          <Heart className="size-6" />
        </span>
        <h3 className="text-xl font-semibold">主动恢复日</h3>
        <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
          让肌肉完成修复和生长。可以做一些轻量有氧、拉伸或散步，保证充足的睡眠与水分。
        </p>
        <div className="mt-6 grid grid-cols-3 gap-6 text-center">
          {[
            { label: "轻量有氧", emoji: "🚶" },
            { label: "全身拉伸", emoji: "🧘" },
            { label: "充足睡眠", emoji: "😴" },
          ].map((item) => (
            <div key={item.label} className="flex flex-col items-center gap-1.5">
              <span className="text-xl">{item.emoji}</span>
              <span className="font-sans text-xs text-muted-foreground">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const totalSets = workout.exercises.reduce((sum, e) => sum + e.sets, 0)

  return (
    <div className="space-y-6">
      {/* Header summary */}
      <div className="flex flex-wrap items-center gap-3">
        <Badge className="bg-brand-green/10 text-brand-green hover:bg-brand-green/15">
          {focusLabel(workout.focus)}
        </Badge>
        <span className="flex items-center gap-1.5 font-sans text-sm text-muted-foreground">
          <Clock className="size-4" />
          预计 {workout.estimated_duration} 分钟
        </span>
        <span className="flex items-center gap-1.5 font-sans text-sm text-muted-foreground">
          <Dumbbell className="size-4" />
          {workout.exercises.length} 个动作 · {totalSets} 组
        </span>
      </div>

      {/* Exercise cards */}
      <div className="space-y-3">
        {workout.exercises.map((exercise, index) => (
          <ExerciseCard key={`${exercise.name}-${index}`} exercise={exercise} index={index} />
        ))}
      </div>
    </div>
  )
}

// ── Today pill indicator ─────────────────────────────────────────

function TodayDot() {
  return (
    <span className="size-1.5 rounded-full bg-primary" aria-label="今天" />
  )
}

// ── Day selector pill ────────────────────────────────────────────

function DayTab({
  day,
  todayIndex,
  isRest,
  focus,
  isActive,
  onClick,
}: {
  day: number
  todayIndex: number
  isRest: boolean
  focus?: string
  isActive: boolean
  onClick: () => void
}) {
  const isToday = day === todayIndex

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex shrink-0 flex-col items-center gap-1 rounded-lg border px-4 py-3 font-sans text-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
        isActive
          ? "border-primary bg-primary/8 text-primary shadow-sm"
          : "border-border bg-card text-muted-foreground hover:border-muted-foreground/30 hover:text-foreground",
      )}
    >
      <span className="flex items-center gap-1.5 font-semibold">
        {DAY_NAMES[day]}
        {isToday && <TodayDot />}
      </span>
      <span className={cn("text-[0.65rem]", isActive ? "text-primary/70" : "text-muted-foreground/60")}>
        {isRest ? "恢复" : focus ? focusLabel(focus) : "训练"}
      </span>
    </button>
  )
}

// ── Empty state ──────────────────────────────────────────────────

function EmptyState({
  hasBodyAnalysis,
  generating,
  onGenerate,
  onAnalysis,
}: {
  hasBodyAnalysis: boolean
  generating: boolean
  onGenerate: () => void
  onAnalysis: () => void
}) {
  return (
    <section className="grid overflow-hidden rounded-lg border border-border bg-card shadow-[0_8px_24px_rgba(23,26,23,0.04)] lg:grid-cols-[1fr_1fr]">
      {/* Hero side */}
      <div className="relative flex min-h-72 flex-col justify-between bg-gradient-to-br from-brand-dark to-[#1f2e25] p-7 text-brand-light sm:p-9">
        <span className="flex size-12 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <CalendarDays className="size-5" />
        </span>
        <div>
          <span className="font-sans text-[0.65rem] font-semibold uppercase tracking-[0.15em] text-brand-light/45">
            No active plan
          </span>
          <h2 className="mt-3 max-w-sm text-2xl font-semibold leading-tight">
            建立第一份可执行的训练计划
          </h2>
          <p className="mt-3 max-w-sm text-sm leading-6 text-brand-light/60">
            {hasBodyAnalysis
              ? "体型分析已完成，现在可以根据你的目标生成本周训练。"
              : "先完成体型分析，AI 会结合你的目标、经验和身体状态安排动作。"}
          </p>
        </div>
        {/* Decorative grid */}
        <div className="pointer-events-none absolute right-0 bottom-0 grid grid-cols-6 gap-1 p-6 opacity-[0.04]">
          {Array.from({ length: 24 }).map((_, i) => (
            <div key={i} className="size-2 rounded-sm bg-current" />
          ))}
        </div>
      </div>

      {/* Steps side */}
      <div className="flex flex-col justify-center p-7 sm:p-9">
        <span className="page-kicker">Getting started</span>
        <ol className="mt-4 space-y-0">
          {[
            { step: "01", title: "建立体型画像", status: hasBodyAnalysis ? "已完成" : "待完成", done: hasBodyAnalysis },
            { step: "02", title: "生成一周训练", status: "当前步骤", done: false },
            { step: "03", title: "按日训练与打卡", status: "生成后开启", done: false },
          ].map((item) => (
            <li
              key={item.step}
              className={cn(
                "flex items-center gap-4 border-b border-border py-4 last:border-b-0",
                item.done && "opacity-50",
              )}
            >
              <span
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-md font-heading text-xs font-semibold",
                  item.done
                    ? "bg-brand-green/10 text-brand-green"
                    : item.status === "当前步骤"
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground",
                )}
              >
                {item.done ? "✓" : item.step}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-sans text-sm font-semibold text-foreground">{item.title}</p>
                <p className="mt-0.5 font-sans text-xs text-muted-foreground">{item.status}</p>
              </div>
              {item.done && (
                <Trophy className="size-4 shrink-0 text-brand-green" />
              )}
            </li>
          ))}
        </ol>
        <div className="mt-7 flex flex-col gap-3 sm:flex-row">
          {!hasBodyAnalysis && (
            <Button variant="outline" onClick={onAnalysis}>
              完成体型分析
              <ArrowRight />
            </Button>
          )}
          <Button onClick={onGenerate} disabled={generating}>
            {generating ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {generating ? "生成中..." : "生成训练计划"}
          </Button>
        </div>
      </div>
    </section>
  )
}

// ── Main page ────────────────────────────────────────────────────

export default function PlanPage() {
  const { userId, user } = useAuth()
  const [plan, setPlan] = useState<TrainingPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeDay, setActiveDay] = useState<number>(new Date().getDay() || 7)

  useEffect(() => {
    if (!userId) return
    let cancelled = false

    const loadPlan = async () => {
      try {
        const response = await getCurrentPlan(userId)
        if (!cancelled) setPlan(response.plan)
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "加载失败")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadPlan()
    return () => {
      cancelled = true
    }
  }, [userId])

  const handleGenerate = async () => {
    if (!userId) return
    setGenerating(true)
    setError(null)
    try {
      const response = await generatePlan(userId, user?.body_analysis || undefined, user?.profile || undefined)
      setPlan(response.plan)
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "生成失败")
    } finally {
      setGenerating(false)
    }
  }

  const todayIndex = new Date().getDay() || 7
  const activeWorkout = plan?.weekly_plan?.find((w) => w.day === activeDay)

  // ── Loading ──
  if (loading) {
    return (
      <div className="page-shell">
        <div className="space-y-3 border-b border-border pb-7">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-10 w-52" />
        </div>
        <Skeleton className="h-[32rem] w-full rounded-lg" />
      </div>
    )
  }

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <span className="page-kicker">Weekly programming</span>
          <h1 className="page-title">训练计划</h1>
          <p className="page-description">
            {plan
              ? `本周从 ${plan.week_start} 开始 · 难度系数 ${plan.difficulty_factor} · 共 ${plan.weekly_plan.length} 天`
              : "把体型画像、训练目标和可用时间整理成一周可执行的训练安排。"}
          </p>
        </div>
        {plan && (
          <Button variant="outline" onClick={handleGenerate} disabled={generating}>
            {generating ? <Loader2 className="animate-spin" /> : <Sparkles />}
            重新生成
          </Button>
        )}
      </header>

      {error && (
        <div
          role="alert"
          className="rounded-lg border-l-2 border-destructive bg-destructive/8 px-4 py-3 font-sans text-sm text-destructive"
        >
          {error}
        </div>
      )}

      {/* ── Empty state ── */}
      {!plan && (
        <EmptyState
          hasBodyAnalysis={Boolean(user?.body_analysis)}
          generating={generating}
          onGenerate={handleGenerate}
          onAnalysis={() => window.location.href = "/analysis"}
        />
      )}

      {/* ── Active plan ── */}
      {plan?.weekly_plan && (
        <section className="space-y-6">
          {/* Day selector pills */}
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            {plan.weekly_plan.map((workout) => (
              <DayTab
                key={workout.day}
                day={workout.day}
                todayIndex={todayIndex}
                isRest={workout.is_rest_day}
                focus={workout.focus}
                isActive={workout.day === activeDay}
                onClick={() => setActiveDay(workout.day)}
              />
            ))}
          </div>

          {/* Active day workout */}
          {activeWorkout && (
            <Card className="overflow-hidden border-border shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
              <CardContent className="p-5 sm:p-6">
                <DayWorkout workout={activeWorkout} />
              </CardContent>
            </Card>
          )}
        </section>
      )}
    </div>
  )
}
