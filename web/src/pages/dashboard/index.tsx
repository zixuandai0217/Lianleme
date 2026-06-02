/* 首页仪表盘：今日训练 + 打卡统计 + 训练打卡 */
import { useEffect, useState, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Flame, Trophy, Calendar, Dumbbell, ArrowRight, CheckCircle2, Loader2, Star } from "lucide-react"
import { getTodayWorkout, getCheckinStats, completeWorkout, getCurrentPlan } from "@/api"
import type { TodayWorkout, CheckInStats } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"

export default function DashboardPage() {
  const { userId } = useAuth()
  const navigate = useNavigate()
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

  const totalSets = today?.exercises?.reduce((sum, ex) => sum + ex.sets, 0) ?? 0

  const loadData = useCallback(async () => {
    if (!userId) return
    try {
      const [t, s] = await Promise.all([
        getTodayWorkout(userId).catch(() => null),
        getCheckinStats(userId).catch(() => null),
        getCurrentPlan(userId).then(r => { setPlanId(r.plan?.id); return r }).catch(() => null),
      ])
      setToday(t)
      setStats(s)
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
    const mins = Number(duration) || 30
    setCheckinLoading(true)
    try {
      const res = await completeWorkout({
        user_id: userId,
        plan_id: planId,
        workout_date: new Date().toISOString().slice(0, 10),
        total_sets: totalSets || sets,
        completed_sets: sets,
        duration_minutes: mins,
        difficulty_rating: difficulty,
      })
      setAiFeedback(res.ai_feedback || null)
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
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">首页</h1>
        <p className="text-muted-foreground">欢迎回来，今天也要加油训练！</p>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">连续打卡</CardTitle>
            <Flame className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.streak_days ?? 0}</div>
            <p className="text-xs text-muted-foreground">天</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">总打卡</CardTitle>
            <Trophy className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.total_checkins ?? 0}</div>
            <p className="text-xs text-muted-foreground">次</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">本月打卡</CardTitle>
            <Calendar className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.monthly_checkins ?? 0}</div>
            <p className="text-xs text-muted-foreground">次</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">月完成率</CardTitle>
            <Dumbbell className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {stats ? `${Math.round(stats.monthly_completion_rate * 100)}%` : "0%"}
            </div>
            <p className="text-xs text-muted-foreground">本月平均</p>
          </CardContent>
        </Card>
      </div>

      {/* Today's workout */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Dumbbell className="h-5 w-5" />
            今日训练
          </CardTitle>
        </CardHeader>
        <CardContent>
          {today?.is_rest_day ? (
            <div className="text-center py-8">
              <p className="text-lg font-medium text-muted-foreground">
                {today.message || "今日休息，好好恢复 💤"}
              </p>
            </div>
          ) : today?.exercises ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{today.focus}</Badge>
                <span className="text-sm text-muted-foreground">
                  预计 {today.estimated_duration} 分钟
                </span>
              </div>
              <div className="grid gap-2">
                {today.exercises.map((ex, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div>
                      <p className="font-medium">{ex.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {ex.sets} 组 × {ex.reps}
                      </p>
                    </div>
                    <Badge variant="outline">{ex.weight_suggestion}</Badge>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Button onClick={() => navigate("/coach")} variant="outline" className="flex-1">
                  AI 陪练
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
                <Button onClick={openCheckinDialog} className="flex-1">
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                  完成打卡
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 space-y-3">
              <p className="text-muted-foreground">暂无训练计划</p>
              <Button variant="outline" onClick={() => navigate("/analysis")}>
                先完成体型分析
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent records */}
      {stats?.recent_records && stats.recent_records.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>最近打卡记录</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {stats.recent_records.slice(0, 5).map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div>
                    <p className="font-medium">{r.workout_date}</p>
                    <p className="text-sm text-muted-foreground">
                      {r.duration_minutes} 分钟
                    </p>
                  </div>
                  <Badge
                    variant={r.completion_rate >= 0.8 ? "default" : "secondary"}
                  >
                    {Math.round(r.completion_rate * 100)}%
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 训练打卡对话框 */}
      <Dialog open={checkinOpen} onOpenChange={setCheckinOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{checkinDone ? "打卡成功" : "训练打卡"}</DialogTitle>
          </DialogHeader>

          {checkinDone ? (
            <div className="space-y-4 py-2">
              <div className="flex flex-col items-center gap-3 py-4">
                <CheckCircle2 className="h-12 w-12 text-green-500" />
                <p className="text-lg font-semibold">今日训练已完成！</p>
              </div>
              {aiFeedback && (
                <div className="rounded-lg bg-muted/50 p-4">
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">{aiFeedback}</p>
                </div>
              )}
              <Button className="w-full" onClick={() => setCheckinOpen(false)}>
                关闭
              </Button>
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="completedSets">完成组数</Label>
                  <Input
                    id="completedSets"
                    type="number"
                    value={completedSets}
                    onChange={(e) => setCompletedSets(e.target.value)}
                    placeholder={String(totalSets)}
                    min={0}
                  />
                  {totalSets > 0 && (
                    <p className="text-xs text-muted-foreground">计划共 {totalSets} 组</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="duration">训练时长 (分钟)</Label>
                  <Input
                    id="duration"
                    type="number"
                    value={duration}
                    onChange={(e) => setDuration(e.target.value)}
                    placeholder="30"
                    min={1}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>训练难度</Label>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Button
                      key={n}
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9"
                      onClick={() => setDifficulty(n)}
                    >
                      <Star
                        className={`h-5 w-5 ${n <= difficulty ? "text-yellow-500 fill-yellow-500" : "text-muted-foreground"}`}
                      />
                    </Button>
                  ))}
                  <span className="flex items-center text-sm text-muted-foreground ml-2">
                    {["", "很轻松", "轻松", "适中", "吃力", "极限"][difficulty]}
                  </span>
                </div>
              </div>

              <DialogFooter>
                <Button onClick={handleCheckin} disabled={checkinLoading} className="w-full">
                  {checkinLoading ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                  )}
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
