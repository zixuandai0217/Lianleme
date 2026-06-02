/* 训练计划页：周视图 + 每日训练详情 + 生成计划 */
import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CalendarDays, Clock, Dumbbell, Loader2, Sparkles } from "lucide-react"
import { getCurrentPlan, generatePlan } from "@/api"
import type { TrainingPlan, DailyWorkout } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"

const DAY_NAMES = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]

function DayCard({ workout }: { workout: DailyWorkout }) {
  if (workout.is_rest_day) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed p-8 text-muted-foreground">
        休息日 · 好好恢复
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <Badge variant="secondary">{workout.focus}</Badge>
        <span className="text-muted-foreground flex items-center gap-1">
          <Clock className="h-3.5 w-3.5" />
          {workout.estimated_duration} 分钟
        </span>
      </div>
      <div className="space-y-2">
        {workout.exercises.map((ex, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-1">
            <div className="flex items-center justify-between">
              <p className="font-medium">{ex.name}</p>
              <Badge variant="outline" className="text-xs">
                {ex.weight_suggestion}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {ex.sets} 组 × {ex.reps} · 组休 {ex.rest_seconds}s
            </p>
            <p className="text-xs text-muted-foreground">{ex.tips}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function PlanPage() {
  const { userId, user } = useAuth()
  const [plan, setPlan] = useState<TrainingPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadPlan = useCallback(async () => {
    if (!userId) return
    try {
      const res = await getCurrentPlan(userId)
      setPlan(res.plan)
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    loadPlan()
  }, [loadPlan])

  const handleGenerate = async () => {
    if (!userId) return
    setGenerating(true)
    setError(null)
    try {
      const res = await generatePlan(userId, user?.body_analysis || undefined, user?.profile || undefined)
      setPlan(res.plan)
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败")
    } finally {
      setGenerating(false)
    }
  }

  const todayIndex = new Date().getDay() || 7

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-96" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">训练计划</h1>
        <div className="flex items-center gap-3">
          <p className="text-muted-foreground">
            {plan
              ? `周计划 · 起始日 ${plan.week_start} · 难度系数 ${plan.difficulty_factor}`
              : "暂无训练计划"}
          </p>
          {plan && (
            <Button variant="outline" size="sm" onClick={handleGenerate} disabled={generating}>
              {generating ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Sparkles className="mr-1 h-3 w-3" />}
              重新生成
            </Button>
          )}
        </div>
      </div>

      {!plan && !loading && (
        <Card className="border-dashed">
          <CardContent className="pt-10 pb-10 flex flex-col items-center gap-4">
            <div className="rounded-full bg-primary/10 p-4">
              <Dumbbell className="h-10 w-10 text-primary" />
            </div>
            <div className="text-center space-y-1">
              <p className="text-lg font-semibold">暂无训练计划</p>
              <p className="text-sm text-muted-foreground">
                {user?.body_analysis
                  ? "体型分析已完成，点击下方按钮生成专属训练方案"
                  : "建议先完成体型分析，AI 将根据你的体型定制方案"}
              </p>
            </div>
            <div className="flex gap-3">
              {!user?.body_analysis && (
                <a href="/analysis">
                  <Button variant="outline">去做体型分析</Button>
                </a>
              )}
              <Button onClick={handleGenerate} disabled={generating}>
                {generating ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                {generating ? "生成中..." : "生成训练计划"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {plan && plan.weekly_plan && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CalendarDays className="h-5 w-5" />
              本周计划
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue={String(todayIndex)}>
              <TabsList className="w-full flex">
                {plan.weekly_plan.map((w) => (
                  <TabsTrigger
                    key={w.day}
                    value={String(w.day)}
                    className="flex-1 text-xs"
                  >
                    <span className="hidden sm:inline">{DAY_NAMES[w.day]}</span>
                    <span className="sm:hidden">{DAY_NAMES[w.day]?.slice(1)}</span>
                    {w.day === todayIndex && (
                      <Dumbbell className="ml-1 h-3 w-3 text-primary" />
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>
              {plan.weekly_plan.map((w) => (
                <TabsContent key={w.day} value={String(w.day)} className="mt-4">
                  <DayCard workout={w} />
                </TabsContent>
              ))}
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
