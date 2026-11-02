/* 训练会话页：当前动作、组内进度、休息倒计时、跳过与收尾打卡入口。 */
import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowRight, CheckCircle2, Dumbbell, Loader2, SkipForward, TimerReset } from "lucide-react"

import {
  completeSessionSet,
  getCurrentWorkoutSession,
  getTodayWorkout,
  skipSessionExercise,
  startWorkoutSession,
} from "@/api"
import type { SessionExercise, WorkoutSessionView } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/hooks/use-auth"
import { resolveTodayState, type TodayState } from "@/lib/today-workout"
import {
  SKIP_REASONS,
  canCompleteSet,
  exerciseVolumeLabel,
  nextExerciseHint,
  overallProgressLabel,
  restCountdownLabel,
  setProgressLabel,
} from "@/lib/workout-session"
import { cn } from "@/lib/utils"

const statusLabels: Record<string, string> = {
  pending: "待训练",
  completed: "已完成",
  skipped: "已跳过",
}

export default function SessionPage() {
  const { userId } = useAuth()
  const navigate = useNavigate()
  const [view, setView] = useState<WorkoutSessionView | null>(null)
  const [todayState, setTodayState] = useState<TodayState>("unavailable")
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [restSeconds, setRestSeconds] = useState<number | null>(null)
  const [skipOpen, setSkipOpen] = useState(false)
  const [skipReason, setSkipReason] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!userId) return
    try {
      const current = await getCurrentWorkoutSession(userId).catch(() => null)
      if (current) {
        setView(current)
        setTodayState("training")
        return
      }
      const today = await getTodayWorkout(userId).catch(() => null)
      setTodayState(resolveTodayState(today))
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    load()
  }, [load])

  const resting = restSeconds !== null
  useEffect(() => {
    if (!resting) return
    const timer = window.setInterval(() => {
      setRestSeconds((value) => {
        if (value === null || value <= 1) {
          window.clearInterval(timer)
          return null
        }
        return value - 1
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [resting])

  const start = async () => {
    if (!userId) return
    setStarting(true)
    setError(null)
    try {
      setView(await startWorkoutSession(userId))
    } catch {
      setError("开始训练失败，请稍后重试")
    } finally {
      setStarting(false)
    }
  }

  const completeSet = async () => {
    if (!view?.current_exercise) return
    const exercise = view.current_exercise
    setSubmitting(true)
    setError(null)
    try {
      const next = await completeSessionSet(view.session_id, exercise.index, exercise.completed_sets)
      setView(next)
      setRestSeconds(exercise.rest_seconds)
    } catch {
      setError("这一组没有记上，请重试")
    } finally {
      setSubmitting(false)
    }
  }

  const submitSkip = async () => {
    if (!view?.current_exercise || !skipReason) return
    setSubmitting(true)
    setError(null)
    try {
      setView(await skipSessionExercise(view.session_id, view.current_exercise.index, skipReason))
      setSkipOpen(false)
      setSkipReason(null)
    } catch {
      setError("跳过失败，请重试")
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="page-shell">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (!view) {
    return (
      <div className="page-shell">
        <header className="page-header">
          <div>
            <span className="page-kicker">Session</span>
            <h1 className="page-title">今日训练</h1>
          </div>
        </header>

        {todayState === "rest" ? (
          <Card>
            <CardContent className="flex min-h-56 flex-col justify-center py-8">
              <h2 className="text-2xl font-semibold">今天是恢复日</h2>
              <p className="mt-3 max-w-xl font-sans text-sm leading-6 text-muted-foreground">
                保持轻量活动，补充水分与睡眠，让下一次训练更有质量。
              </p>
              <Button variant="outline" className="mt-7 w-fit" onClick={() => navigate("/coach")}>
                咨询恢复建议
                <ArrowRight />
              </Button>
            </CardContent>
          </Card>
        ) : todayState === "no_plan" ? (
          <Card>
            <CardContent className="flex min-h-56 flex-col justify-center py-8">
              <h2 className="text-2xl font-semibold">还没有本周训练计划</h2>
              <p className="mt-3 max-w-xl font-sans text-sm leading-6 text-muted-foreground">
                先完成体型分析并生成一份本周计划，之后就能开始今天的训练。
              </p>
              <div className="mt-7 flex gap-3">
                <Button variant="outline" onClick={() => navigate("/analysis")}>
                  先做体型分析
                </Button>
                <Button onClick={() => navigate("/plan")}>
                  去生成计划
                  <ArrowRight />
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : todayState === "training" ? (
          <Card>
            <CardContent className="flex min-h-56 flex-col justify-center py-8">
              <h2 className="text-2xl font-semibold">准备好就开始</h2>
              <p className="mt-3 max-w-xl font-sans text-sm leading-6 text-muted-foreground">
                开始后每一组都会记录下来；中途退出再回来会接着上次的进度。
              </p>
              <Button className="mt-7 w-fit" disabled={starting} onClick={start}>
                {starting ? <Loader2 className="animate-spin" /> : <Dumbbell />}
                开始训练
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="flex min-h-56 flex-col justify-center py-8">
              <h2 className="text-2xl font-semibold">暂时拿不到今天的安排</h2>
              <p className="mt-3 max-w-xl font-sans text-sm leading-6 text-muted-foreground">
                网络或服务波动都可能影响加载，稍后刷新即可。
              </p>
              <Button variant="outline" className="mt-7 w-fit" onClick={load}>
                重新加载
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    )
  }

  const current = view.current_exercise
  const nextHint = nextExerciseHint(view)

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <span className="page-kicker">Session</span>
          <h1 className="page-title">今日训练</h1>
          <p className="page-description">
            {overallProgressLabel(view.progress)} · 完成 {view.progress.percent}%
            {view.session_date ? ` · ${view.session_date}` : ""}
          </p>
        </div>
        <Badge variant={view.finished ? "secondary" : "default"}>
          {view.finished ? "已练完" : "进行中"}
        </Badge>
      </header>

      {error && <p className="font-sans text-sm text-destructive">{error}</p>}

      <div className="h-2 overflow-hidden rounded-full bg-secondary">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${view.progress.percent}%` }}
        />
      </div>

      <Card>
        <CardHeader className="border-b pb-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="page-kicker text-primary">Current</span>
              <CardTitle className="text-xl">
                {current ? current.name : "全部动作已处理完"}
              </CardTitle>
            </div>
            {current && setProgressLabel(current) && (
              <Badge variant="secondary">{setProgressLabel(current)}</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-5 py-6">
          {current ? (
            <>
              <div className="flex flex-wrap items-center gap-3 font-sans text-sm text-muted-foreground">
                <span>{exerciseVolumeLabel(current)}</span>
                <span>{current.weight_suggestion}</span>
                <span>组间休息 {current.rest_seconds}s</span>
              </div>
              <p className="font-sans text-sm leading-6 text-muted-foreground">{current.tips}</p>

              {view.status !== "in_progress" ? (
                <div className="rounded-md border border-border bg-secondary/40 px-4 py-3">
                  <p className="font-sans text-sm text-muted-foreground">
                    这次训练已经结束，只能查看进度；新的一天会开启新的会话。
                  </p>
                </div>
              ) : resting ? (
                <div className="flex items-center gap-3 rounded-md border border-primary/30 bg-primary/[0.04] px-4 py-3">
                  <TimerReset className="size-4 text-primary" />
                  <span className="font-sans text-sm font-semibold">
                    {restCountdownLabel(restSeconds ?? 0)}
                  </span>
                  <Button variant="ghost" size="sm" onClick={() => setRestSeconds(null)}>
                    跳过休息
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Button
                    className="flex-1"
                    disabled={submitting || !canCompleteSet(view, resting)}
                    onClick={completeSet}
                  >
                    {submitting ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                    完成一组
                  </Button>
                  <Button variant="outline" className="flex-1" onClick={() => setSkipOpen(true)}>
                    <SkipForward />
                    跳过这个动作
                  </Button>
                </div>
              )}

              {nextHint && (
                <p className="font-sans text-xs text-muted-foreground">{nextHint}</p>
              )}
            </>
          ) : (
            <div className="flex flex-col gap-3">
              <p className="font-sans text-sm text-muted-foreground">
                这次训练的动作都处理完了，去收尾打卡，看看今天的完成情况。
              </p>
              {view.can_checkin && (
                <Button className="w-fit" onClick={() => navigate("/?checkin=1")}>
                  收尾并打卡
                  <ArrowRight />
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <section aria-labelledby="session-exercises-title">
        <div className="section-heading">
          <div>
            <span className="page-kicker">Plan</span>
            <h2 id="session-exercises-title" className="section-title">
              今天的动作
            </h2>
          </div>
        </div>
        <ul className="mt-3 divide-y divide-border border-y border-border">
          {view.exercises.map((exercise: SessionExercise) => (
            <li key={exercise.index} className="flex items-center justify-between gap-4 py-3.5">
              <div className="min-w-0">
                <p
                  className={cn(
                    "font-sans text-sm font-semibold",
                    exercise.status !== "pending" && "text-muted-foreground",
                  )}
                >
                  {exercise.order}. {exercise.name}
                </p>
                <p className="mt-1 font-sans text-xs text-muted-foreground">
                  {exerciseVolumeLabel(exercise)} · 已完成 {exercise.completed_sets}/{exercise.sets} 组
                  {exercise.skip_reason ? ` · ${exercise.skip_reason}` : ""}
                </p>
              </div>
              <Badge variant={exercise.status === "pending" ? "outline" : "secondary"}>
                {statusLabels[exercise.status] ?? exercise.status}
              </Badge>
            </li>
          ))}
        </ul>
      </section>

      <Dialog open={skipOpen} onOpenChange={setSkipOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>跳过这个动作</DialogTitle>
          </DialogHeader>
          <p className="font-sans text-sm text-muted-foreground">
            跳过不会计入完成组数，选一个原因，方便以后排计划时参考。
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {SKIP_REASONS.map((reason) => (
              <Button
                key={reason}
                type="button"
                variant={skipReason === reason ? "default" : "outline"}
                size="sm"
                onClick={() => setSkipReason(reason)}
              >
                {reason}
              </Button>
            ))}
          </div>
          <DialogFooter className="mt-5">
            <Button variant="outline" onClick={() => setSkipOpen(false)}>
              取消
            </Button>
            <Button disabled={!skipReason || submitting} onClick={submitSkip}>
              确认跳过
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
