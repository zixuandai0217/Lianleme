/* 体重记录页：记录体重 + SVG 趋势折线图 + 历史列表 */
import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Scale,
  TrendingDown,
  TrendingUp,
  Minus,
  Plus,
  Trash2,
  Loader2,
  ArrowDown,
  ArrowUp,
} from "lucide-react"
import { addWeightRecord, getWeightTrend, deleteWeightRecord } from "@/api"
import type { WeightTrend } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"

/** 纯 SVG 折线图组件，支持单点显示 */
function TrendChart({ trend }: { trend: WeightTrend }) {
  const data = trend.records
  const weights = data.map((r) => r.weight)
  const minW = Math.floor(Math.min(...weights) - 2)
  const maxW = Math.ceil(Math.max(...weights) + 2)
  const rangeW = maxW - minW || 1

  const W = 600
  const H = 200
  const padX = 45
  const padY = 25
  const chartW = W - padX * 2
  const chartH = H - padY * 2

  const yTicks = 5
  const yLabels = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = minW + (rangeW * i) / yTicks
    return { val: Math.round(val * 10) / 10, y: padY + (1 - i / yTicks) * chartH }
  })

  if (data.length === 1) {
    const cy = padY + (1 - (data[0].weight - minW) / rangeW) * chartH
    const cx = W / 2
    return (
      <div className="space-y-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
          {yLabels.map((l) => (
            <g key={l.val}>
              <line x1={padX} y1={l.y} x2={W - padX} y2={l.y} className="stroke-border" strokeWidth={0.5} />
              <text x={padX - 6} y={l.y + 4} textAnchor="end" className="fill-muted-foreground" fontSize={10}>{l.val}</text>
            </g>
          ))}
          <line x1={padX} y1={cy} x2={W - padX} y2={cy} className="stroke-primary/30" strokeWidth={1} strokeDasharray="6 4" />
          <circle cx={cx} cy={cy} r={6} className="fill-primary/20" />
          <circle cx={cx} cy={cy} r={4} className="fill-primary" />
          <text x={cx} y={cy - 12} textAnchor="middle" className="fill-foreground font-semibold" fontSize={13}>{data[0].weight} kg</text>
          <text x={cx} y={H - 2} textAnchor="middle" className="fill-muted-foreground" fontSize={9}>{data[0].recorded_date}</text>
        </svg>
        <p className="text-center text-xs text-muted-foreground">坚持每天记录，趋势线就会出现</p>
      </div>
    )
  }

  const points = data.map((r, i) => ({
    x: padX + (i / (data.length - 1)) * chartW,
    y: padY + (1 - (r.weight - minW) / rangeW) * chartH,
    weight: r.weight,
    date: r.recorded_date,
  }))

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ")
  const areaD = `${pathD} L ${points[points.length - 1].x} ${padY + chartH} L ${points[0].x} ${padY + chartH} Z`

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
      {yLabels.map((l) => (
        <g key={l.val}>
          <line x1={padX} y1={l.y} x2={W - padX} y2={l.y} className="stroke-border" strokeWidth={0.5} />
          <text x={padX - 6} y={l.y + 4} textAnchor="end" className="fill-muted-foreground" fontSize={10}>{l.val}</text>
        </g>
      ))}
      <path d={areaD} className="fill-primary/10" />
      <path d={pathD} fill="none" className="stroke-primary" strokeWidth={2} strokeLinejoin="round" />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={3.5} className="fill-primary" />
          {(i === 0 || i === points.length - 1) && (
            <text x={p.x} y={p.y - 8} textAnchor="middle" className="fill-foreground font-medium" fontSize={11}>{p.weight}</text>
          )}
        </g>
      ))}
      <text x={points[0].x} y={H - 2} textAnchor="start" className="fill-muted-foreground" fontSize={9}>{data[0].recorded_date}</text>
      <text x={points[points.length - 1].x} y={H - 2} textAnchor="end" className="fill-muted-foreground" fontSize={9}>{data[data.length - 1].recorded_date}</text>
    </svg>
  )
}

export default function WeightPage() {
  const { userId } = useAuth()
  const [trend, setTrend] = useState<WeightTrend | null>(null)
  const [loading, setLoading] = useState(true)
  const [weightInput, setWeightInput] = useState("")
  const [noteInput, setNoteInput] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [days, setDays] = useState(90)

  const loadTrend = useCallback(async () => {
    if (!userId) return
    try {
      const t = await getWeightTrend(userId, days)
      setTrend(t)
    } finally {
      setLoading(false)
    }
  }, [userId, days])

  useEffect(() => {
    loadTrend()
  }, [loadTrend])

  const handleSubmit = async () => {
    if (!userId || !weightInput) return
    setSubmitting(true)
    try {
      await addWeightRecord(userId, Number(weightInput), undefined, noteInput || undefined)
      setWeightInput("")
      setNoteInput("")
      await loadTrend()
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (recordId: number) => {
    if (!userId) return
    await deleteWeightRecord(userId, recordId)
    await loadTrend()
  }

  const adjust = (delta: number) => {
    const current = weightInput ? Number(weightInput) : trend?.current_weight || 0
    if (current > 0) setWeightInput(String(Math.round((current + delta) * 10) / 10))
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">体重记录</h1>
        <p className="text-muted-foreground">记录每日体重，追踪身体变化趋势</p>
      </div>

      {/* Quick input */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Scale className="h-5 w-5" />
            记录今日体重
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-end gap-3">
            <div className="flex-1 space-y-2">
              <Label htmlFor="weight">体重 (kg)</Label>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline" size="icon"
                  onClick={() => adjust(-0.1)}
                  disabled={!weightInput && !trend?.current_weight}
                >
                  <Minus className="h-4 w-4" />
                </Button>
                <Input
                  id="weight"
                  type="number"
                  step="0.1"
                  placeholder={trend?.current_weight ? String(trend.current_weight) : "输入体重"}
                  value={weightInput}
                  onChange={(e) => setWeightInput(e.target.value)}
                  className="text-center text-lg font-semibold"
                />
                <Button
                  variant="outline" size="icon"
                  onClick={() => adjust(0.1)}
                  disabled={!weightInput && !trend?.current_weight}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="flex-1 space-y-2">
              <Label htmlFor="note">备注 (可选)</Label>
              <Input
                id="note"
                placeholder="如：跑步日、聚餐后..."
                value={noteInput}
                onChange={(e) => setNoteInput(e.target.value)}
              />
            </div>
          </div>
          <Button onClick={handleSubmit} disabled={submitting || !weightInput} className="w-full">
            {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Scale className="mr-2 h-4 w-4" />}
            记录
          </Button>
        </CardContent>
      </Card>

      {/* Stats summary — 多条记录才显示完整统计 */}
      {trend && trend.total > 0 && (
        <div className={`grid gap-4 ${trend.total >= 2 ? "sm:grid-cols-4" : "sm:grid-cols-1 max-w-xs"}`}>
          <Card>
            <CardContent className="pt-4 pb-3 text-center">
              <p className="text-xs text-muted-foreground mb-1">当前体重</p>
              <p className="text-2xl font-bold">{trend.current_weight ?? "-"}</p>
              <p className="text-xs text-muted-foreground">kg</p>
            </CardContent>
          </Card>
          {trend.total >= 2 && (
            <>
              <Card>
                <CardContent className="pt-4 pb-3 text-center">
                  <p className="text-xs text-muted-foreground mb-1">总变化</p>
                  <p className={`text-2xl font-bold flex items-center justify-center gap-1 ${
                    (trend.change ?? 0) < 0 ? "text-green-600" : (trend.change ?? 0) > 0 ? "text-red-500" : ""
                  }`}>
                    {(trend.change ?? 0) < 0 ? <ArrowDown className="h-5 w-5" /> : (trend.change ?? 0) > 0 ? <ArrowUp className="h-5 w-5" /> : null}
                    {trend.change != null ? Math.abs(trend.change) : "-"}
                  </p>
                  <p className="text-xs text-muted-foreground">kg</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3 text-center">
                  <p className="text-xs text-muted-foreground mb-1">最低</p>
                  <p className="text-2xl font-bold text-green-600">{trend.min_weight ?? "-"}</p>
                  <p className="text-xs text-muted-foreground">kg</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3 text-center">
                  <p className="text-xs text-muted-foreground mb-1">最高</p>
                  <p className="text-2xl font-bold text-red-500">{trend.max_weight ?? "-"}</p>
                  <p className="text-xs text-muted-foreground">kg</p>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      )}

      {/* Trend chart */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              {(trend?.change ?? 0) <= 0 ? (
                <TrendingDown className="h-5 w-5 text-green-600" />
              ) : (
                <TrendingUp className="h-5 w-5 text-red-500" />
              )}
              体重趋势
            </CardTitle>
            <div className="flex gap-1">
              {[30, 90, 180, 365].map((d) => (
                <Button
                  key={d}
                  variant={days === d ? "default" : "outline"}
                  size="sm"
                  className="text-xs px-2 h-7"
                  onClick={() => setDays(d)}
                >
                  {d <= 90 ? `${d}天` : `${Math.round(d / 30)}月`}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : trend && trend.total > 0 ? (
            <TrendChart trend={trend} />
          ) : (
            <div className="flex items-center justify-center h-48 text-muted-foreground">
              暂无体重记录，快来记录第一笔吧
            </div>
          )}
        </CardContent>
      </Card>

      {/* History list */}
      {trend && trend.records.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>历史记录</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[...trend.records].reverse().map((r, i, arr) => {
                const prev = arr[i + 1]
                const diff = prev ? Math.round((r.weight - prev.weight) * 100) / 100 : null
                return (
                  <div key={r.id} className="flex items-center justify-between rounded-lg border p-3">
                    <div className="flex items-center gap-3">
                      <div>
                        <p className="font-semibold text-lg">{r.weight} <span className="text-sm font-normal text-muted-foreground">kg</span></p>
                        <p className="text-xs text-muted-foreground">{r.recorded_date}</p>
                      </div>
                      {r.note && (
                        <Badge variant="secondary" className="text-xs">{r.note}</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {diff != null && diff !== 0 && (
                        <span className={`text-xs font-medium ${diff < 0 ? "text-green-600" : "text-red-500"}`}>
                          {diff > 0 ? "+" : ""}{diff}
                        </span>
                      )}
                      <Button
                        variant="ghost" size="icon" className="h-8 w-8"
                        onClick={() => handleDelete(r.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
