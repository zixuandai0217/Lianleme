/* Coach-led dashboard with training status, contextual actions, and check-in states. */
import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  ArrowRight,
  BotMessageSquare,
  Calendar,
  Camera,
  CheckCircle2,
  ClipboardList,
  Dumbbell,
  Flame,
  Loader2,
  Scale,
  Star,
  Trophy,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { DigitalCoach, type DigitalCoachState } from "@/components/digital-coach"
import { completeWorkout, getCheckinStats, getCurrentPlan, getTodayWorkout } from "@/api"
import type { CheckInStats, TodayWorkout } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"

const coachActions = [
  { title: "看体型", detail: "拍照分析", to: "/analysis", icon: Camera },
  { title: "排训练", detail: "本周计划", to: "/plan", icon: ClipboardList },
  { title: "问教练", detail: "即时建议", to: "/coach", icon: BotMessageSquare },
  { title: "记体重", detail: "更新记录", to: "/weight", icon: Scale },
]

interface CoachState {
  eyebrow: string
  title: string
  message: string
  primaryTo: string
  characterState: DigitalCoachState
}

// Turn the user's current training data into one clear recommendation.
function getCoachState(hasBodyAnalysis: boolean, planId: number | undefined, today: TodayWorkout | null): CoachState {
  if (!hasBodyAnalysis) {
    return {
      eyebrow: "先认识你",
      title: "拍一张自然站姿照，我们从身体状态开始。",
      message: "我会整理你的优势与训练重点，再把结果变成一份能执行的计划。",
      primaryTo: "/analysis",
      characterState: "thinking",
    }
  }

  if (!planId) {
    return {
      eyebrow: "画像已就绪",
      title: "下一步，把目标排进这一周。",
      message: "基于你的体型分析生成训练安排，动作、组数和休息时间会一起准备好。",
      primaryTo: "/plan",
      characterState: "idle",
    }
  }

  if (today?.is_rest_day) {
    return {
      eyebrow: "恢复日",
      title: "今天不用硬练，把恢复也算进进步里。",
      message: today.message || "保持轻量活动，补充水分，有疑问就随时问我。",
      primaryTo: "/coach",
      characterState: "idle",
    }
  }

  if (today?.exercises?.length) {
    return {
      eyebrow: "今日训练",
      title: `${today.focus || "今天"}，我们按 ${today.estimated_duration || 30} 分钟的节奏完成。`,
      message: `共 ${today.exercises.length} 个动作、${today.exercises.reduce((sum, exercise) => sum + exercise.sets, 0)} 组。遇到不熟悉的动作可以直接问我。`,
      primaryTo: "/plan",
      characterState: "speaking",
    }
  }

  return {
    eyebrow: "教练在线",
    title: "告诉我你今天的状态，我来帮你决定怎么练。",
    message: "你可以查看计划，也可以直接问一个训练、饮食或恢复问题。",
    primaryTo: "/coach",
    characterState: "idle",
  }
}

export default function DashboardPage() {
  const { userId, user } = useAuth()
  const navigate = useNavigate()
  const hasBodyAnalysis = Boolean(user?.body_analysis)
  const [today, setToday] = useState<TodayWorkout | null>(null)
  const [stats, setStats] = useState<CheckInStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [checkinOpen, setCheckinOpen] = useState(false)
  const [checkinLoading, setCheckinLoading] = useState(false)
  const [checkinDone, setCheckinDone] = useState(false)
  const [aiFeedback, setAiFeedback] = useState<string | null>(null)
  const [planId, setPlanId] = useState<number | undefined>()
  const [completedSets, setCompletedSets] = useState("")
  const [duration, setDuration] = useState("")
  const [difficulty, setDifficulty] = useState(3)

  const totalSets = today?.exercises?.reduce((sum, exercise) => sum + exercise.sets, 0) ?? 0
  const formattedDate = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date())

  const loadData = useCallback(async () => {
    if (!userId) return
    try {
      const [todayResponse, statsResponse] = await Promise.all([
        getTodayWorkout(userId).catch(() => null),
        getCheckinStats(userId).catch(() => null),
        getCurrentPlan(userId)
          .then((response) => {
            setPlanId(response.plan?.id)
            return response
          })
          .catch(() => null),
      ])
      setToday(todayResponse)
      setStats(statsResponse)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleCheckin = async () => {
    if (!userId) return
    const sets = Number(completedSets) || totalSets
    const minutes = Number(duration) || 30
    setCheckinLoading(true)
    try {
      const response = await completeWorkout({
        user_id: userId,
        plan_id: planId,
        workout_date: new Date().toISOString().slice(0, 10),
        total_sets: totalSets || sets,
        completed_sets: sets,
        duration_minutes: minutes,
        difficulty_rating: difficulty,
      })
      setAiFeedback(response.ai_feedback || null)
      setCheckinDone(true)
      loadData()
    } catch {
      setAiFeedback("打卡提交失败，请稍后重试")
    } finally {
      setCheckinLoading(false)
    }
  }

  const openCheckinDialog = () => {
    setCompletedSets(String(totalSets))
    setDuration("30")
    setDifficulty(3)
    setCheckinDone(false)
    setAiFeedback(null)
    setCheckinOpen(true)
  }

  if (loading) {
    return (
      <div className="page-shell">
        <div className="space-y-3 border-b border-border pb-7">
          <Skeleton className="h-3 w-28" />
          <Skeleton className="h-10 w-64" />
        </div>
        <Skeleton className="h-40" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((item) => <Skeleton key={item} className="h-32" />)}
        </div>
        <Skeleton className="h-72" />
      </div>
    )
  }

  const coachState = getCoachState(hasBodyAnalysis, planId, today)
  const recommendedAction = coachActions.find((action) => action.to === coachState.primaryTo) ?? coachActions[2]
  const secondaryActions = coachActions.filter((action) => action.to !== recommendedAction.to)
  const RecommendedIcon = recommendedAction.icon

  const metricItems = [
    { label: "连续打卡", value: stats?.streak_days ?? 0, unit: "天", icon: Flame, className: "border-t-primary", iconClass: "text-primary" },
    { label: "总打卡", value: stats?.total_checkins ?? 0, unit: "次", icon: Trophy, className: "border-t-brand-green", iconClass: "text-brand-green" },
    { label: "本月打卡", value: stats?.monthly_checkins ?? 0, unit: "次", icon: Calendar, className: "border-t-brand-blue", iconClass: "text-brand-blue" },
    {
      label: "月完成率",
      value: stats ? `${Math.round(stats.monthly_completion_rate * 100)}%` : "0%",
      unit: "本月平均",
      icon: Dumbbell,
      className: "border-t-foreground",
      iconClass: "text-foreground",
    },
  ]

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <span className="page-kicker">Training desk</span>
          <h1 className="page-title">{user?.nickname ? `${user.nickname}，今天怎么练？` : "今天怎么练？"}</h1>
          <p className="page-description">
            {formattedDate} · 我已经把最值得先做的事放在前面。
          </p>
        </div>
        <div className="hidden items-center gap-2 rounded-md border border-border bg-card px-3 py-2 font-sans text-xs text-muted-foreground shadow-sm sm:flex">
          <span className="size-2 rounded-full bg-brand-green" />
          数字教练在线
        </div>
      </header>

      <section
        aria-labelledby="digital-coach-title"
        className="overflow-hidden rounded-lg bg-brand-dark text-brand-light shadow-[0_18px_50px_rgba(23,35,28,0.14)]"
      >
        <div className="relative md:grid md:min-h-64 md:grid-cols-[minmax(0,1fr)_13rem]">
          <div className="relative z-10 flex flex-col justify-center px-5 py-6 pr-24 sm:px-7 sm:py-7 sm:pr-28 md:px-8 md:py-8 md:pr-8">
            <div className="flex items-center gap-2 font-sans text-xs font-semibold text-[#a9c5ad]">
              <span className="size-2 rounded-full bg-[#a9c5ad]" />
              {coachState.eyebrow}
            </div>
            <h2 id="digital-coach-title" className="mt-3 max-w-2xl text-xl leading-tight font-semibold text-brand-light sm:text-2xl md:text-3xl">
              {coachState.title}
            </h2>
            <p className="mt-3 max-w-xl font-sans text-sm leading-6 text-brand-light/62">
              {coachState.message}
            </p>
            <span className="mt-5 font-sans text-[0.68rem] font-semibold uppercase text-brand-light/55 [letter-spacing:0.1em]">建议下一步</span>
            <Button className="mt-2 w-fit" onClick={() => navigate(recommendedAction.to)}>
              <RecommendedIcon className="size-4" />
              {recommendedAction.title}
              <span className="hidden text-primary-foreground sm:inline">· {recommendedAction.detail}</span>
              <ArrowRight className="size-4" />
            </Button>
          </div>

          <div className="absolute top-4 right-4 grid size-20 place-items-center overflow-hidden rounded-full border border-white/12 bg-white/5 shadow-inner sm:size-24 md:static md:size-auto md:min-h-64 md:rounded-none md:border-y-0 md:border-r-0 md:border-l md:bg-white/[0.035]">
            <DigitalCoach
              ariaLabel={`数字教练正在提供建议：${coachState.title}`}
              state={coachState.characterState}
              variant="portrait"
            />
            <span className="absolute right-2 bottom-2 size-3 rounded-full border-2 border-brand-dark bg-[#8eb396] md:right-5 md:bottom-5 md:size-3.5" />
          </div>
        </div>

        <div className="grid grid-cols-3 border-t border-white/12 bg-black/8">
          {secondaryActions.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.to}
                type="button"
                onClick={() => navigate(item.to)}
                className="group flex min-h-17 cursor-pointer items-center justify-center gap-2 border-r border-white/12 px-2 py-3 text-brand-light/65 transition-colors last:border-r-0 hover:bg-white/8 hover:text-brand-light focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 sm:min-h-19 sm:justify-start sm:px-5"
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-white/8 text-brand-light/80 group-hover:bg-white/12">
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0 text-center sm:text-left">
                  <span className="block font-sans text-xs font-semibold text-brand-light sm:text-sm">{item.title}</span>
                  <span className="mt-0.5 hidden font-sans text-xs text-brand-light/55 sm:block">{item.detail}</span>
                </span>
              </button>
            )
          })}
        </div>
      </section>

      <section aria-labelledby="metrics-title">
        <div className="section-heading">
          <div>
            <span className="page-kicker">Consistency</span>
            <h2 id="metrics-title" className="section-title">训练节奏</h2>
          </div>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {metricItems.map((metric) => {
            const Icon = metric.icon
            return (
              <div key={metric.label} className={`rounded-md border border-border border-t-2 bg-card px-4 py-4 shadow-[0_8px_24px_rgba(23,26,23,0.04)] ${metric.className}`}>
                <div className="flex items-center justify-between gap-3">
                  <span className="font-sans text-xs text-muted-foreground">{metric.label}</span>
                  <Icon className={`size-4 ${metric.iconClass}`} />
                </div>
                <div className="mt-4 flex items-baseline gap-2">
                  <span className="metric-value">{metric.value}</span>
                  <span className="font-sans text-xs text-muted-foreground">{metric.unit}</span>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1.65fr)_minmax(17rem,0.75fr)]" aria-labelledby="today-workout-title">
        <Card>
          <CardHeader className="border-b pb-5 sm:flex sm:flex-row sm:items-end sm:justify-between">
            <div>
              <span className="page-kicker text-primary">Today</span>
              <CardTitle id="today-workout-title" className="text-xl">今日训练</CardTitle>
            </div>
            {today && !today.is_rest_day && (
              <div className="flex items-center gap-2 font-sans text-xs text-muted-foreground">
                <Badge className="bg-brand-green text-brand-light">{today.focus}</Badge>
                <span>{today.estimated_duration} 分钟</span>
              </div>
            )}
          </CardHeader>
          <CardContent>
            {today?.is_rest_day ? (
              <div className="flex min-h-56 flex-col justify-center py-6">
                <h3 className="text-2xl font-semibold">今天留给恢复</h3>
                <p className="mt-3 max-w-xl font-sans text-sm leading-6 text-muted-foreground">
                  {today.message || "保持轻量活动，补充水分，让下一次训练更有质量。"}
                </p>
                <Button variant="outline" className="mt-7 w-fit" onClick={() => navigate("/coach")}>
                  咨询恢复建议
                  <ArrowRight />
                </Button>
              </div>
            ) : today?.exercises ? (
              <div className="space-y-6">
                <div className="divide-y divide-border border-y border-border">
                  {today.exercises.map((exercise, index) => (
                    <div key={`${exercise.name}-${index}`} className="grid gap-2 py-4 sm:grid-cols-[2.5rem_1fr_auto] sm:items-center">
                      <span className="font-heading text-xs font-semibold text-primary">{String(index + 1).padStart(2, "0")}</span>
                      <div>
                        <p className="font-sans font-semibold">{exercise.name}</p>
                        <p className="mt-1 font-sans text-sm text-muted-foreground">{exercise.sets} 组 × {exercise.reps}</p>
                      </div>
                      <Badge variant="outline" className="justify-self-start sm:justify-self-end">
                        {exercise.weight_suggestion}
                      </Badge>
                    </div>
                  ))}
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Button variant="outline" className="flex-1" onClick={() => navigate("/coach")}>
                    AI 陪练
                    <ArrowRight />
                  </Button>
                  <Button className="flex-1" onClick={openCheckinDialog}>
                    <CheckCircle2 />
                    完成打卡
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex min-h-56 flex-col justify-center py-6">
                <h3 className="text-2xl font-semibold">今天还没有训练安排</h3>
                <p className="mt-3 max-w-lg font-sans text-sm leading-6 text-muted-foreground">完成体型分析后，生成一份与你当前状态匹配的周计划。</p>
                <Button className="mt-7 w-fit" onClick={() => navigate("/analysis")}>
                  先完成体型分析
                  <ArrowRight />
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b pb-5">
            <span className="page-kicker">Recent activity</span>
            <CardTitle>最近打卡</CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.recent_records && stats.recent_records.length > 0 ? (
              <div className="divide-y divide-border border-y border-border">
                {stats.recent_records.slice(0, 5).map((record) => (
                  <div key={record.id} className="flex items-center justify-between gap-4 py-3.5">
                    <div>
                      <p className="font-sans text-sm font-semibold">{record.workout_date}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{record.duration_minutes} 分钟</p>
                    </div>
                    <Badge variant={record.completion_rate >= 0.8 ? "default" : "secondary"}>
                      {Math.round(record.completion_rate * 100)}%
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex min-h-52 flex-col items-center justify-center text-center">
                <span className="flex size-10 items-center justify-center rounded-sm bg-secondary text-brand-blue">
                  <Calendar className="size-4" />
                </span>
                <p className="mt-4 font-sans text-sm font-semibold">还没有打卡记录</p>
                <p className="mt-1 max-w-52 text-sm leading-5 text-muted-foreground">完成一次训练后，这里会形成你的连续性记录。</p>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <Dialog open={checkinOpen} onOpenChange={setCheckinOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{checkinDone ? "打卡成功" : "训练打卡"}</DialogTitle>
          </DialogHeader>

          {checkinDone ? (
            <div className="space-y-4 py-2">
              <div className="flex flex-col items-center gap-3 py-4">
                <span className="flex size-14 items-center justify-center rounded-sm bg-brand-green/15 text-brand-green">
                  <CheckCircle2 className="size-7" />
                </span>
                <p className="font-sans text-lg font-semibold">今日训练已完成</p>
              </div>
              {aiFeedback && (
                <div className="border-l-2 border-brand-green bg-brand-green/8 p-4">
                  <p className="text-sm leading-6 text-muted-foreground whitespace-pre-wrap">{aiFeedback}</p>
                </div>
              )}
              <Button className="w-full" onClick={() => setCheckinOpen(false)}>关闭</Button>
            </div>
          ) : (
            <div className="space-y-5 py-2">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="completedSets">完成组数</Label>
                  <Input
                    id="completedSets"
                    type="number"
                    value={completedSets}
                    onChange={(event) => setCompletedSets(event.target.value)}
                    placeholder={String(totalSets)}
                    min={0}
                  />
                  {totalSets > 0 && <p className="text-xs text-muted-foreground">计划共 {totalSets} 组</p>}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="duration">训练时长（分钟）</Label>
                  <Input
                    id="duration"
                    type="number"
                    value={duration}
                    onChange={(event) => setDuration(event.target.value)}
                    placeholder="30"
                    min={1}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label id="difficulty-label">训练难度</Label>
                <div className="flex flex-wrap items-center gap-1" role="radiogroup" aria-labelledby="difficulty-label">
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <Button
                      key={rating}
                      type="button"
                      variant="ghost"
                      size="icon"
                      role="radio"
                      aria-checked={rating === difficulty}
                      aria-label={`训练难度 ${rating}`}
                      onClick={() => setDifficulty(rating)}
                    >
                      <Star className={`size-5 ${rating <= difficulty ? "fill-primary text-primary" : "text-muted-foreground"}`} />
                    </Button>
                  ))}
                  <span className="ml-2 font-sans text-sm text-muted-foreground">
                    {["", "很轻松", "轻松", "适中", "吃力", "极限"][difficulty]}
                  </span>
                </div>
              </div>

              <DialogFooter>
                <Button onClick={handleCheckin} disabled={checkinLoading} className="w-full">
                  {checkinLoading ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                  {checkinLoading ? "提交中..." : "提交打卡"}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
