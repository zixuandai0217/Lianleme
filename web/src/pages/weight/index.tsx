/* Body data hub: fitness profile + weight tracking + trend chart + history. */
import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Activity,
  ArrowUpDown,
  Flame,
  History,
  Loader2,
  Minus,
  Plus,
  Ruler,
  Save,
  Scale,
  Sparkles,
  Trash2,
  TrendingDown,
  TrendingUp,
} from "lucide-react"
import { addWeightRecord, deleteWeightRecord, getWeightTrend, updateProfile } from "@/api"
import type { WeightTrend } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"
import { cn } from "@/lib/utils"

// ── Options ──────────────────────────────────────────────────────

const GOALS = [
  { value: "减脂", icon: Flame },
  { value: "增肌", icon: Sparkles },
  { value: "塑形", icon: Activity },
  { value: "提升体能", icon: ArrowUpDown },
]

const EXPERIENCE_LEVELS = ["新手", "初级", "中级", "高级"]

function OptionGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: readonly T[] | { value: T; icon?: React.ComponentType<{ className?: string }> }[]
  value: T
  onChange: (v: T) => void
}) {
  const items = options.map((opt) =>
    typeof opt === "string" ? { value: opt as T } : opt,
  )
  return (
    <div className="space-y-1.5">
      <Label className="font-sans text-xs font-semibold text-muted-foreground">{label}</Label>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => {
          const Icon = (item as { icon?: React.ComponentType<{ className?: string }> }).icon
          const isActive = value === item.value
          return (
            <Button
              key={item.value}
              type="button"
              variant={isActive ? "default" : "outline"}
              size="sm"
              onClick={() => onChange(item.value)}
              className={cn("gap-1.5 transition-all", isActive && "shadow-sm")}
            >
              {Icon && <Icon className="size-3.5" />}
              {item.value}
            </Button>
          )
        })}
      </div>
    </div>
  )
}

// ── SVG trend chart ──────────────────────────────────────────────

function TrendChart({ trend }: { trend: WeightTrend }) {
  const data = trend.records
  const weights = data.map((r) => r.weight)
  const minW = Math.floor(Math.min(...weights) - 2)
  const maxW = Math.ceil(Math.max(...weights) + 2)
  const rangeW = maxW - minW || 1

  const W = 600, H = 200, padX = 45, padY = 25
  const chartW = W - padX * 2, chartH = H - padY * 2

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
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="体重趋势图">
          {yLabels.map((l) => (
            <g key={l.val}>
              <line x1={padX} y1={l.y} x2={W - padX} y2={l.y} className="stroke-border" strokeWidth={0.5} />
              <text x={padX - 6} y={l.y + 4} textAnchor="end" className="fill-muted-foreground" fontSize={10}>{l.val}</text>
            </g>
          ))}
          <line x1={padX} y1={cy} x2={W - padX} y2={cy} className="stroke-primary/20" strokeWidth={1} strokeDasharray="6 4" />
          <circle cx={cx} cy={cy} r={6} className="fill-primary/15" />
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
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="体重趋势图">
      <defs>
        <linearGradient id="wg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {yLabels.map((l) => (
        <g key={l.val}>
          <line x1={padX} y1={l.y} x2={W - padX} y2={l.y} className="stroke-border" strokeWidth={0.5} />
          <text x={padX - 6} y={l.y + 4} textAnchor="end" className="fill-muted-foreground" fontSize={10}>{l.val}</text>
        </g>
      ))}
      <path d={areaD} fill="url(#wg)" />
      <path d={pathD} fill="none" className="stroke-primary" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={3.5} className="fill-primary" />
          <circle cx={p.x} cy={p.y} r={5} className="fill-primary/15" />
          {(i === 0 || i === points.length - 1) && (
            <text x={p.x} y={p.y - 10} textAnchor="middle" className="fill-foreground font-medium" fontSize={11}>{p.weight}</text>
          )}
        </g>
      ))}
      <text x={points[0].x} y={H - 2} textAnchor="start" className="fill-muted-foreground" fontSize={9}>{data[0].recorded_date}</text>
      <text x={points[points.length - 1].x} y={H - 2} textAnchor="end" className="fill-muted-foreground" fontSize={9}>{data[data.length - 1].recorded_date}</text>
    </svg>
  )
}

// ── Main page ────────────────────────────────────────────────────

export default function WeightPage() {
  const { userId, user, refreshUser } = useAuth()

  // Profile state
  const [synced, setSynced] = useState(false)
  const [height, setHeight] = useState("")
  const [age, setAge] = useState("")
  const [gender, setGender] = useState("")
  const [goal, setGoal] = useState("")
  const [experience, setExperience] = useState("")
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)

  // Weight tracking state
  const [trend, setTrend] = useState<WeightTrend | null>(null)
  const [loading, setLoading] = useState(true)
  const [weightInput, setWeightInput] = useState("")
  const [noteInput, setNoteInput] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [days, setDays] = useState(90)

  // Sync profile data once
  if (user && !synced) {
    setHeight(String(user.profile?.height || ""))
    setAge(String(user.profile?.age || ""))
    setGender(user.profile?.gender || "")
    setGoal(user.profile?.goal || "")
    setExperience(user.profile?.experience || "")
    setSynced(true)
  }

  // Load weight trend
  const loadTrend = useCallback(async () => {
    if (!userId) return
    try {
      const t = await getWeightTrend(userId, days)
      setTrend(t)
    } finally {
      setLoading(false)
    }
  }, [userId, days])

  useEffect(() => { loadTrend() }, [loadTrend])

  // Save profile
  const handleSaveProfile = async () => {
    if (!userId) return
    setProfileSaving(true)
    setProfileSaved(false)
    try {
      await updateProfile(userId, {
        profile: {
          height: height ? Number(height) : undefined,
          age: age ? Number(age) : undefined,
          gender: gender || undefined,
          goal: goal || undefined,
          experience: experience || undefined,
        },
      })
      await refreshUser()
      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 2000)
    } finally {
      setProfileSaving(false)
    }
  }

  // Record weight
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
    <div className="page-shell !max-w-5xl">
      <header className="page-header">
        <div>
          <span className="page-kicker">Body data</span>
          <h1 className="page-title">身体数据</h1>
          <p className="page-description">管理身体档案与体重趋势，掌握长期变化。</p>
        </div>
      </header>

      {/* ── Body profile ── */}
      <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
        <div className="border-b border-border px-6 py-4">
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            <Ruler className="size-4 text-primary" />
            身体档案
          </h2>
        </div>
        <div className="space-y-5 p-6">
          <div className="grid gap-5 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-height" className="font-sans text-xs font-semibold text-muted-foreground">身高 (cm)</Label>
              <Input id="p-height" type="number" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="170" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-age" className="font-sans text-xs font-semibold text-muted-foreground">年龄</Label>
              <Input id="p-age" type="number" value={age} onChange={(e) => setAge(e.target.value)} placeholder="25" />
            </div>
            <div className="space-y-1.5">
              <Label className="font-sans text-xs font-semibold text-muted-foreground">性别</Label>
              <div className="flex gap-2 pt-0.5">
                {["男", "女"].map((g) => (
                  <Button key={g} type="button" variant={gender === g ? "default" : "outline"} size="sm" onClick={() => setGender(g)} className={cn("min-w-16", gender === g && "shadow-sm")}>
                    {g}
                  </Button>
                ))}
              </div>
            </div>
          </div>

          <Separator />

          <div className="grid gap-5 sm:grid-cols-2">
            <OptionGroup label="健身目标" options={GOALS} value={goal} onChange={setGoal} />
            <OptionGroup label="训练经验" options={EXPERIENCE_LEVELS} value={experience} onChange={setExperience} />
          </div>

          <Button onClick={handleSaveProfile} disabled={profileSaving}>
            {profileSaving ? <Loader2 className="animate-spin" /> : profileSaved ? null : <Save />}
            {profileSaved ? "已保存 ✓" : "保存档案"}
          </Button>
        </div>
      </section>

      {/* ── Quick weight input ── */}
      <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
        <div className="border-b border-border px-6 py-4">
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            <Scale className="size-4 text-primary" />
            记录今日体重
          </h2>
        </div>
        <div className="space-y-5 p-6">
          <div className="grid items-end gap-4 sm:grid-cols-[1fr_auto]">
            <div className="min-w-0 space-y-2">
              <Label htmlFor="weight" className="font-sans text-xs font-semibold text-muted-foreground">体重 (kg)</Label>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="icon" aria-label="减少 0.1" onClick={() => adjust(-0.1)} disabled={!weightInput && !trend?.current_weight}>
                  <Minus className="size-4" />
                </Button>
                <Input id="weight" type="number" step="0.1" placeholder={trend?.current_weight ? String(trend.current_weight) : "输入体重"} value={weightInput} onChange={(e) => setWeightInput(e.target.value)} className="text-center text-lg font-semibold tabular-nums" />
                <Button variant="outline" size="icon" aria-label="增加 0.1" onClick={() => adjust(0.1)} disabled={!weightInput && !trend?.current_weight}>
                  <Plus className="size-4" />
                </Button>
              </div>
            </div>
            <div className="min-w-0 space-y-2 sm:w-52">
              <Label htmlFor="note" className="font-sans text-xs font-semibold text-muted-foreground">备注 (可选)</Label>
              <Input id="note" placeholder="如：跑步日、聚餐后..." value={noteInput} onChange={(e) => setNoteInput(e.target.value)} />
            </div>
          </div>
          <Button onClick={handleSubmit} disabled={submitting || !weightInput}>
            {submitting ? <Loader2 className="animate-spin" /> : <Scale />}
            记录
          </Button>
        </div>
      </section>

      {/* ── Stats summary ── */}
      {trend && trend.total > 0 && (
        <div className={cn("grid gap-4", trend.total >= 2 ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-1 max-w-xs")}>
          {[
            { label: "当前体重", value: trend.current_weight ?? "-", unit: "kg", color: "text-foreground" },
            ...(trend.total >= 2 ? [
              { label: "总变化", value: trend.change != null ? `${trend.change > 0 ? "+" : ""}${Math.abs(trend.change).toFixed(1)}` : "-", unit: "kg", color: (trend.change ?? 0) < 0 ? "text-brand-green" : (trend.change ?? 0) > 0 ? "text-destructive" : "text-foreground" },
              { label: "最低", value: trend.min_weight ?? "-", unit: "kg", color: "text-brand-green" },
              { label: "最高", value: trend.max_weight ?? "-", unit: "kg", color: "text-destructive" },
            ] : []),
          ].map((stat) => (
            <div key={stat.label} className="rounded-lg border border-border bg-card px-5 py-5 shadow-[0_2px_8px_rgba(23,26,23,0.03)]">
              <p className="font-sans text-xs text-muted-foreground">{stat.label}</p>
              <p className={cn("mt-2 font-heading text-2xl font-semibold tabular-nums", stat.color)}>{stat.value}</p>
              <p className="mt-0.5 font-sans text-xs text-muted-foreground">{stat.unit}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Trend chart ── */}
      <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            {(trend?.change ?? 0) <= 0 ? <TrendingDown className="size-4 text-brand-green" /> : <TrendingUp className="size-4 text-destructive" />}
            体重趋势
          </h2>
          <div className="flex gap-1">
            {[30, 90, 180, 365].map((d) => (
              <Button key={d} variant={days === d ? "default" : "outline"} size="sm" className="h-7 px-2 text-xs" onClick={() => setDays(d)}>
                {d <= 90 ? `${d}天` : `${Math.round(d / 30)}月`}
              </Button>
            ))}
          </div>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="flex h-48 items-center justify-center text-muted-foreground"><Loader2 className="size-6 animate-spin" /></div>
          ) : trend && trend.total > 0 ? (
            <TrendChart trend={trend} />
          ) : (
            <div className="flex h-48 flex-col items-center justify-center text-muted-foreground">
              <span className="mb-3 flex size-12 items-center justify-center rounded-lg bg-muted text-muted-foreground/50"><Ruler className="size-5" /></span>
              <p className="text-sm font-medium">暂无体重记录</p>
              <p className="mt-1 text-xs text-muted-foreground">快来记录第一笔吧</p>
            </div>
          )}
        </div>
      </section>

      {/* ── History list ── */}
      {trend && trend.records.length > 0 && (
        <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
          <div className="border-b border-border px-6 py-4">
            <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
              <History className="size-4 text-primary" />
              历史记录
            </h2>
          </div>
          <div className="p-6">
            <div className="space-y-2">
              {[...trend.records].reverse().map((r, i, arr) => {
                const prev = arr[i + 1]
                const diff = prev ? Math.round((r.weight - prev.weight) * 100) / 100 : null
                return (
                  <div key={r.id} className="flex items-center justify-between rounded-lg border border-border px-4 py-3 transition-colors hover:bg-accent/20">
                    <div className="flex items-center gap-4">
                      <span className="font-heading text-lg font-semibold tabular-nums">
                        {r.weight}<span className="ml-0.5 font-sans text-sm font-normal text-muted-foreground">kg</span>
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="font-sans text-xs text-muted-foreground">{r.recorded_date}</span>
                        {diff != null && diff !== 0 && (
                          <span className={cn("font-sans text-xs font-medium tabular-nums", diff < 0 ? "text-brand-green" : "text-destructive")}>
                            {diff > 0 ? "+" : ""}{diff}
                          </span>
                        )}
                      </div>
                      {r.note && <Badge variant="secondary" className="text-[0.6rem]">{r.note}</Badge>}
                    </div>
                    <Button variant="ghost" size="icon-sm" aria-label="删除记录" onClick={() => handleDelete(r.id)}>
                      <Trash2 className="size-3.5 text-muted-foreground hover:text-destructive" />
                    </Button>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
