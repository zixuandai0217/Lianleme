/* Refined body analysis page with polished upload, results, and history sections. */
import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import {
  ScanEye,
  Loader2,
  CheckCircle2,
  XCircle,
  History,
  ChevronDown,
  ChevronUp,
  BarChart3,
  Sparkles,
  ArrowRight,
  Camera,
  Trophy,
  Target,
} from "lucide-react"
import { generatePlan, getAnalysisHistory, getAnalyzeResult, getCurrentPlan, startAnalyze } from "@/api"
import type { BodyAnalysisResult, BodyAnalysisRecordItem } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"
import { buildAnalysisJourney } from "./flow"
import { cn } from "@/lib/utils"

export default function AnalysisPage() {
  const { userId, user, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [imageBase64, setImageBase64] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [planGenerating, setPlanGenerating] = useState(false)
  const [planReady, setPlanReady] = useState(false)
  const [result, setResult] = useState<BodyAnalysisResult | null>(
    (user?.body_analysis as BodyAnalysisResult) || null,
  )
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const fileRef = useRef<HTMLInputElement>(null)
  const [history, setHistory] = useState<BodyAnalysisRecordItem[]>([])
  const [expandedRecord, setExpandedRecord] = useState<number | null>(null)
  const [expandedHistoryScores, setExpandedHistoryScores] = useState<number | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [showScores, setShowScores] = useState(false)

  // Track whether the user has explicitly cleared the result (uploaded new photo)
  const clearedByUpload = useRef(false)

  // Sync result with user data on mount (before any upload action)
  useEffect(() => {
    if (user?.body_analysis && !clearedByUpload.current && !result) {
      setResult(user.body_analysis as BodyAnalysisResult)
    }
  }, [user?.body_analysis]) // eslint-disable-line react-hooks/exhaustive-deps

  // Check if user already has a plan from a previous session
  useEffect(() => {
    if (!userId) return
    getCurrentPlan(userId)
      .then((res) => {
        if (res.plan?.id) setPlanReady(true)
      })
      .catch(() => { /* no plan exists */ })
  }, [userId])

  const journey = buildAnalysisJourney({
    hasImage: Boolean(imageBase64),
    analyzing,
    hasResult: Boolean(result),
    planGenerating,
    hasPlan: planReady,
  })

  const handleFile = useCallback((file: File) => {
    if (!file.type.startsWith("image/")) return
    clearedByUpload.current = true
    const reader = new FileReader()
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string
      setImagePreview(dataUrl)
      setImageBase64(dataUrl.split(",")[1])
      setResult(null)
      setPlanReady(false)
      setError(null)
      setActionError(null)
    }
    reader.readAsDataURL(file)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const startAnalysis = async () => {
    if (!userId || !imageBase64) return
    setAnalyzing(true)
    setError(null)
    setActionError(null)
    setPlanReady(false)
    setProgress(10)

    try {
      const { task_id } = await startAnalyze(userId, imageBase64, user?.profile || undefined)
      setProgress(30)

      const MAX_POLL_RETRIES = 60
      const poll = async (attempt = 0): Promise<BodyAnalysisResult> => {
        if (attempt >= MAX_POLL_RETRIES) throw new Error("分析超时，请稍后重试")
        const res = await getAnalyzeResult(task_id)
        if (res.status === "completed" && res.result) return res.result
        if (res.status === "failed") throw new Error(res.error || "分析失败")
        setProgress((p) => Math.min(p + 10, 90))
        await new Promise((r) => setTimeout(r, 2000))
        return poll(attempt + 1)
      }

      const analysisResult = await poll()
      setResult(analysisResult)
      setProgress(100)
      await refreshUser()
      refreshHistory()
    } catch (e) {
      setError(e instanceof Error ? e.message : "分析失败")
    } finally {
      setAnalyzing(false)
    }
  }

  const handleJourneyAction = async (target: "generate-plan" | "view-plan" | "go-coach") => {
    if (target === "view-plan") {
      navigate("/plan")
      return
    }
    if (target === "go-coach") {
      navigate("/coach")
      return
    }
    if (!userId || !result) return

    setPlanGenerating(true)
    setActionError(null)
    try {
      await generatePlan(userId, result, user?.profile || undefined)
      setPlanReady(true)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "训练计划生成失败")
    } finally {
      setPlanGenerating(false)
    }
  }

  const refreshHistory = useCallback(async () => {
    if (!userId) return
    setHistoryLoading(true)
    try {
      const res = await getAnalysisHistory(userId)
      setHistory(res.records)
    } catch {
      /* 静默失败 */
    } finally {
      setHistoryLoading(false)
    }
  }, [userId])

  useEffect(() => {
    refreshHistory()
  }, [refreshHistory])

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return ""
    const d = new Date(dateStr)
    return d.toLocaleDateString("zh-CN", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
  }

  const bodyTypeLabels: Record<string, string> = {
    ectomorph: "瘦长型",
    mesomorph: "运动型",
    endomorph: "力量型",
  }

  const muscleLabels: Record<string, string> = {
    head: "头部", neck: "颈部", shoulders: "肩部", chest: "胸部",
    back: "背部", upper_back: "上背", lower_back: "下背",
    abdomen: "腹部", obliques: "侧腹", core: "核心",
    hips: "髋部", glutes: "臀部",
    quadriceps: "股四头", hamstrings: "腘绳肌", calves: "小腿",
    biceps: "肱二头", triceps: "肱三头", forearms: "前臂",
    traps: "斜方肌", lats: "背阔肌", deltoids: "三角肌",
  }
  const t = (key: string) => muscleLabels[key] || key

  return (
    <div className="page-shell">
      <header className="page-header">
        <div>
          <span className="page-kicker">Body assessment</span>
          <h1 className="page-title">体型分析</h1>
          <p className="page-description">
            上传一张全身照，AI 将分析你的体型并给出训练建议
          </p>
        </div>
      </header>

      {/* ── Analysis flow journey ── */}
      <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
        <div className="border-b border-border px-6 py-4">
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            <Target className="size-4 text-primary" />
            分析闭环
          </h2>
        </div>
        <div className="grid gap-4 px-6 py-6 sm:grid-cols-2 md:grid-cols-4">
          {journey.stages.map((stage, index) => {
            const stageIcons: Record<string, React.ComponentType<{ className?: string }>> = {
              upload: Camera,
              analyze: BarChart3,
              plan: Sparkles,
              train: Target,
            }
            const Icon = stageIcons[stage.key]
            const isCompleted = stage.status === "completed"
            const isActive = stage.status === "active"
            return (
              <div
                key={stage.key}
                className={cn(
                  "flex items-start gap-3 rounded-lg border p-4 transition-colors",
                  isCompleted && "border-primary/20 bg-primary/[0.02]",
                  isActive && "border-primary/40 bg-primary/[0.04]",
                  !isCompleted && !isActive && "border-border bg-card",
                )}
              >
                {/* Circle indicator */}
                <span
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                    isCompleted && "bg-primary text-primary-foreground",
                    isActive && "bg-primary/10 text-primary ring-2 ring-primary/20",
                    !isCompleted && !isActive && "bg-muted text-muted-foreground",
                  )}
                >
                  {isCompleted ? (
                    <CheckCircle2 className="size-3.5" />
                  ) : (
                    index + 1
                  )}
                </span>

                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-1.5">
                    {Icon && <Icon className={cn("size-3.5", isActive ? "text-primary" : "text-muted-foreground/50")} />}
                    <p className={cn("text-sm font-semibold", isActive && "text-primary")}>
                      {stage.label}
                    </p>
                  </div>
                  <p className="text-xs leading-5 text-muted-foreground">{stage.description}</p>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Upload + Results grid ── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Upload area */}
        <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
          <div className="border-b border-border px-6 py-4">
            <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
              <Camera className="size-4 text-primary" />
              上传照片
            </h2>
          </div>
          <div className="space-y-5 p-6">
            <button
              type="button"
              aria-label="选择体型分析照片"
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileRef.current?.click()}
              className={cn(
                "flex min-h-[260px] w-full cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-all",
                imagePreview
                  ? "border-primary/20 bg-primary/[0.02] hover:border-primary/40"
                  : "border-border hover:border-primary/60 hover:bg-accent/40",
                "focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
              )}
            >
              {imagePreview ? (
                <img
                  src={imagePreview}
                  alt="预览"
                  className="max-h-56 rounded-md object-contain"
                />
              ) : (
                <>
                  <span className="mb-3 flex size-14 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <ScanEye className="size-6" />
                  </span>
                  <p className="text-sm font-semibold text-foreground">拖拽照片到此处，或点击选择</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    支持 JPG、PNG 格式 · 建议穿着贴身衣物拍摄全身照
                  </p>
                </>
              )}
            </button>
            <input
              id="analysis-photo"
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleFile(f)
              }}
            />

            {analyzing && (
              <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/[0.02] p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                  <Loader2 className="size-4 animate-spin" />
                  {journey.title}
                </div>
                <Progress value={progress} className="h-2" />
                <p className="text-xs text-muted-foreground">{journey.stages[1]?.description}</p>
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
                <XCircle className="size-4 shrink-0" />
                {error}
              </div>
            )}

            <Button
              className="w-full"
              disabled={!imageBase64 || analyzing}
              onClick={startAnalysis}
            >
              {analyzing ? (
                <><Loader2 className="animate-spin" /> 分析中...</>
              ) : (
                "开始分析"
              )}
            </Button>
          </div>
        </section>

        {/* Results */}
        <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
          <div className="border-b border-border px-6 py-4">
            <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
              <CheckCircle2 className="size-4 text-primary" />
              分析结果
            </h2>
          </div>
          <div className="p-6">
            {result ? (
              <div className="space-y-5">
                {/* Overview badges */}
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="bg-brand-green/10 px-3 py-1 text-base text-brand-green hover:bg-brand-green/15">
                    {bodyTypeLabels[result.body_type] || result.body_type}
                  </Badge>
                  <Badge variant="outline" className="border-muted-foreground/20">
                    体脂 {result.body_fat_range}
                  </Badge>
                </div>

                {/* AI summary */}
                <div className="rounded-lg border-l-2 border-brand-green bg-muted/40 p-4">
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
                    {result.summary}
                  </p>
                </div>

                {/* Strengths & weaknesses */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <span className="flex items-center gap-1.5 text-xs font-semibold text-brand-green">
                      <Trophy className="size-3.5" />
                      优势部位
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {result.strengths.map((s) => (
                        <Badge key={s} variant="secondary" className="bg-brand-green/8 text-xs">{t(s)}</Badge>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <span className="flex items-center gap-1.5 text-xs font-semibold text-destructive">
                      <Target className="size-3.5" />
                      需加强
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {result.weak_muscles.map((m) => (
                        <Badge key={m} variant="outline" className="border-destructive/20 bg-destructive/5 text-destructive text-xs">{t(m)}</Badge>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Muscle scores (collapsible) */}
                {result.muscle_scores && Object.keys(result.muscle_scores).length > 0 && (
                  <div className="overflow-hidden rounded-lg border border-border">
                    <button
                      type="button"
                      className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left transition-colors hover:bg-accent/30"
                      onClick={() => setShowScores(!showScores)}
                    >
                      <span className="flex items-center gap-2 text-sm font-medium">
                        <BarChart3 className="size-4 text-muted-foreground" />
                        部位评分详情
                        <Badge variant="secondary" className="text-[0.6rem] font-normal">{Object.keys(result.muscle_scores).length} 项</Badge>
                      </span>
                      {showScores ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
                    </button>
                    {showScores && (
                      <div className="border-t border-border px-4 pb-4 pt-3 space-y-2.5">
                        {Object.entries(result.muscle_scores).map(([part, score]) => (
                          <div key={part} className="flex items-center gap-3">
                            <span className="w-16 shrink-0 text-sm text-muted-foreground">{t(part)}</span>
                            <Progress value={score * 10} className="flex-1 h-2" />
                            <span className="w-10 text-right text-sm text-muted-foreground tabular-nums">{score}/10</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Journey actions */}
                <div className="rounded-lg border border-primary/10 bg-primary/[0.02] p-5">
                  <div className="space-y-1">
                    <p className="text-sm font-semibold">{journey.title}</p>
                    <p className="text-sm text-muted-foreground">{journey.description}</p>
                  </div>

                  <div className="mt-4 grid gap-2">
                    {journey.primaryAction && (
                      <Button
                        onClick={() => handleJourneyAction(journey.primaryAction!.target)}
                        disabled={planGenerating}
                        className="w-full justify-between"
                      >
                        <span className="flex items-center gap-2">
                          {planGenerating ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                          {planGenerating ? "生成中..." : journey.primaryAction.label}
                        </span>
                        <ArrowRight className="size-4" />
                      </Button>
                    )}
                    {journey.secondaryAction && (
                      <Button
                        variant="outline"
                        onClick={() => handleJourneyAction(journey.secondaryAction!.target)}
                        className="w-full justify-between"
                      >
                        <span>{journey.secondaryAction.label}</span>
                        <ArrowRight className="size-4" />
                      </Button>
                    )}
                  </div>

                  {journey.primaryAction && (
                    <p className="mt-3 text-xs text-muted-foreground">{journey.primaryAction.hint}</p>
                  )}

                  {actionError && (
                    <div className="mt-3 flex items-center gap-2 text-sm text-destructive">
                      <XCircle className="size-4" />
                      {actionError}
                    </div>
                  )}

                  {planReady && (
                    <div className="mt-3 rounded-lg border border-primary/20 bg-background/80 px-3 py-2 text-xs text-muted-foreground">
                      本次分析结果已经接入训练计划，现在可以直接继续进入计划执行。
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <span className="mb-4 flex size-14 items-center justify-center rounded-lg bg-muted text-muted-foreground/60">
                  <ScanEye className="size-6" />
                </span>
                <p className="text-sm font-medium">上传照片后查看分析结果</p>
                <p className="mt-1 text-xs text-muted-foreground">AI 将评估你的体型、体脂和肌肉状态</p>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* ── History ── */}
      <section className="rounded-lg border border-border bg-card shadow-[0_4px_16px_rgba(23,26,23,0.04)]">
        <div className="border-b border-border px-6 py-4">
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            <History className="size-4 text-primary" />
            历史分析记录
            {history.length > 0 && (
              <Badge variant="secondary" className="ml-1">{history.length}</Badge>
            )}
          </h2>
        </div>
        <div className="p-6">
          {historyLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="size-5 animate-spin mr-2" />
              <span className="text-sm">加载中...</span>
            </div>
          ) : history.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <span className="mb-3 flex size-12 items-center justify-center rounded-lg bg-muted text-muted-foreground/50">
                <History className="size-5" />
              </span>
              <p className="text-sm font-medium">暂无历史记录</p>
              <p className="mt-1 text-xs text-muted-foreground">完成一次体型分析后将自动保存</p>
            </div>
          ) : (
            <div className="space-y-3">
              {history.map((record) => {
                const isExpanded = expandedRecord === record.id
                return (
                  <div
                    key={record.id}
                    className="overflow-hidden rounded-lg border border-border transition-colors hover:bg-accent/20"
                  >
                    <button
                      type="button"
                      className="flex w-full items-center gap-4 p-4 text-left"
                      onClick={() => setExpandedRecord(isExpanded ? null : record.id)}
                    >
                      {record.image_thumbnail && (
                        <img
                          src={`data:image/jpeg;base64,${record.image_thumbnail}`}
                          alt="缩略图"
                          className="h-14 w-14 shrink-0 rounded-lg object-cover"
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="secondary" className="bg-brand-green/8 text-xs text-brand-green">
                            {bodyTypeLabels[record.result.body_type] || record.result.body_type}
                          </Badge>
                          <Badge variant="outline" className="text-xs">体脂 {record.result.body_fat_range}</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">{formatDate(record.created_at)}</p>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="size-4 shrink-0 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
                      )}
                    </button>

                    {isExpanded && (
                      <div className="border-t border-border px-4 pb-4 pt-3 space-y-3">
                        <div className="rounded-lg bg-muted/40 p-3">
                          <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">{record.result.summary}</p>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <p className="text-xs font-medium mb-1.5 text-brand-green">优势部位</p>
                            <div className="flex flex-wrap gap-1">
                              {record.result.strengths.map((s) => (
                                <Badge key={s} variant="secondary" className="bg-brand-green/8 text-[0.6rem]">{t(s)}</Badge>
                              ))}
                            </div>
                          </div>
                          <div>
                            <p className="text-xs font-medium mb-1.5 text-destructive">需加强</p>
                            <div className="flex flex-wrap gap-1">
                              {record.result.weak_muscles.map((m) => (
                                <Badge key={m} variant="outline" className="border-destructive/20 bg-destructive/5 text-destructive text-[0.6rem]">{t(m)}</Badge>
                              ))}
                            </div>
                          </div>
                        </div>

                        {record.result.muscle_scores && Object.keys(record.result.muscle_scores).length > 0 && (
                          <div className="overflow-hidden rounded-lg border border-border">
                            <button
                              type="button"
                              className="flex w-full items-center justify-between p-2.5 text-left transition-colors hover:bg-accent/30"
                              onClick={(e) => {
                                e.stopPropagation()
                                setExpandedHistoryScores(expandedHistoryScores === record.id ? null : record.id)
                              }}
                            >
                              <span className="flex items-center gap-1.5 text-xs font-medium">
                                <BarChart3 className="size-3.5 text-muted-foreground" />
                                部位评分详情
                                <Badge variant="secondary" className="text-[0.55rem] font-normal px-1.5">{Object.keys(record.result.muscle_scores).length} 项</Badge>
                              </span>
                              {expandedHistoryScores === record.id ? <ChevronUp className="size-3.5 text-muted-foreground" /> : <ChevronDown className="size-3.5 text-muted-foreground" />}
                            </button>
                            {expandedHistoryScores === record.id && (
                              <div className="border-t border-border px-2.5 pb-2.5 pt-2 space-y-1.5">
                                {Object.entries(record.result.muscle_scores).map(([part, score]) => (
                                  <div key={part} className="flex items-center gap-2">
                                    <span className="w-14 shrink-0 text-xs text-muted-foreground">{t(part)}</span>
                                    <Progress value={(score as number) * 10} className="flex-1 h-1.5" />
                                    <span className="w-8 text-right text-xs text-muted-foreground tabular-nums">{score as number}/10</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
