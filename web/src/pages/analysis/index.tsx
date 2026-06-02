/* 体型分析页：图片拖拽上传 + 轮询结果 + 结果展示 + 历史记录 */
import { useState, useCallback, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Upload, ScanEye, Loader2, CheckCircle2, XCircle, History, ChevronDown, ChevronUp, BarChart3, Sparkles, ArrowRight } from "lucide-react"
import { startAnalyze, getAnalyzeResult, getAnalysisHistory, generatePlan } from "@/api"
import type { BodyAnalysisResult, BodyAnalysisRecordItem } from "@/api/types"
import { useAuth } from "@/hooks/use-auth"
import { buildAnalysisJourney } from "./flow"

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
  const journey = buildAnalysisJourney({
    hasImage: Boolean(imageBase64),
    analyzing,
    hasResult: Boolean(result),
    planGenerating,
    hasPlan: planReady,
  })

  const handleFile = useCallback((file: File) => {
    if (!file.type.startsWith("image/")) return
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

  /** 肌群英文 → 中文映射 */
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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">体型分析</h1>
        <p className="text-muted-foreground">
          上传一张全身照，AI 将分析你的体型并给出训练建议
        </p>
      </div>

      <Card>
        <CardHeader className="space-y-2">
          <CardTitle className="text-base">分析闭环</CardTitle>
          <p className="text-sm text-muted-foreground">{journey.description}</p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-4">
            {journey.stages.map((stage, index) => {
              const statusClasses =
                stage.status === "completed"
                  ? "border-primary/30 bg-primary/5"
                  : stage.status === "active"
                    ? "border-primary/50 bg-accent/40"
                    : "border-dashed bg-muted/20"
              const badgeClasses =
                stage.status === "completed"
                  ? "bg-primary text-primary-foreground"
                  : stage.status === "active"
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground"
              return (
                <div
                  key={stage.key}
                  className={`rounded-lg border p-4 transition-colors ${statusClasses}`}
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <span className={`inline-flex h-7 min-w-7 items-center justify-center rounded-full px-2 text-xs font-semibold ${badgeClasses}`}>
                      {index + 1}
                    </span>
                    <Badge variant={stage.status === "completed" ? "default" : "secondary"}>
                      {stage.status === "completed" ? "已完成" : stage.status === "active" ? "进行中" : "待进行"}
                    </Badge>
                  </div>
                  <p className="text-sm font-medium">{stage.label}</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{stage.description}</p>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Upload area */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5" />
              上传照片
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileRef.current?.click()}
              className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors hover:border-primary/50 hover:bg-accent/50 min-h-[280px]"
            >
              {imagePreview ? (
                <img
                  src={imagePreview}
                  alt="预览"
                  className="max-h-64 rounded-lg object-contain"
                />
              ) : (
                <>
                  <ScanEye className="h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-sm font-medium">拖拽照片到此处，或点击选择</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    支持 JPG、PNG 格式
                  </p>
                </>
              )}
            </div>
            <input
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
              <div className="mt-4 space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {journey.title}
                </div>
                <Progress value={progress} />
                <p className="text-xs text-muted-foreground">
                  {journey.stages[1]?.description}
                </p>
              </div>
            )}

            {error && (
              <div className="mt-4 flex items-center gap-2 text-sm text-destructive">
                <XCircle className="h-4 w-4" />
                {error}
              </div>
            )}

            <Button
              className="w-full mt-4"
              disabled={!imageBase64 || analyzing}
              onClick={startAnalysis}
            >
              {analyzing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  分析中...
                </>
              ) : (
                "开始分析"
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Result */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              分析结果
            </CardTitle>
          </CardHeader>
          <CardContent>
            {result ? (
              <div className="space-y-4">
                {/* 总览：体型 + 体脂 */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge className="text-base px-3 py-1">{bodyTypeLabels[result.body_type] || result.body_type}</Badge>
                  <Badge variant="outline">体脂 {result.body_fat_range}</Badge>
                </div>

                {/* AI 建议（核心摘要，置顶） */}
                <div className="rounded-lg bg-muted/50 p-4">
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
                    {result.summary}
                  </p>
                </div>

                {/* 优势 & 弱势 */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-sm font-medium mb-2">优势部位</p>
                    <div className="flex flex-wrap gap-1">
                      {result.strengths.map((s) => (
                        <Badge key={s} variant="secondary">{t(s)}</Badge>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-sm font-medium mb-2">需加强</p>
                    <div className="flex flex-wrap gap-1">
                      {result.weak_muscles.map((m) => (
                        <Badge key={m} variant="destructive">{t(m)}</Badge>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 部位评分（可折叠） */}
                {result.muscle_scores &&
                  Object.keys(result.muscle_scores).length > 0 && (
                    <div className="rounded-lg border">
                      <button
                        className="flex w-full items-center justify-between p-3 text-left hover:bg-accent/30 transition-colors rounded-lg"
                        onClick={() => setShowScores(!showScores)}
                      >
                        <span className="flex items-center gap-2 text-sm font-medium">
                          <BarChart3 className="h-4 w-4" />
                          部位评分详情
                          <Badge variant="secondary" className="text-xs font-normal">
                            {Object.keys(result.muscle_scores).length} 项
                          </Badge>
                        </span>
                        {showScores ? (
                          <ChevronUp className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        )}
                      </button>
                      {showScores && (
                        <div className="border-t px-3 pb-3 pt-2 space-y-2">
                          {Object.entries(result.muscle_scores).map(
                            ([part, score]) => (
                              <div key={part} className="flex items-center gap-3">
                                <span className="text-sm w-20 shrink-0">{t(part)}</span>
                                <Progress value={score * 10} className="flex-1" />
                                <span className="text-sm text-muted-foreground w-10 text-right">
                                  {score}/10
                                </span>
                              </div>
                            ),
                          )}
                        </div>
                      )}
                    </div>
                  )}

                <div className="rounded-xl border bg-primary/5 p-4">
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
                          {planGenerating ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Sparkles className="h-4 w-4" />
                          )}
                          {planGenerating ? "生成中..." : journey.primaryAction.label}
                        </span>
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    )}

                    {journey.secondaryAction && (
                      <Button
                        variant="outline"
                        onClick={() => handleJourneyAction(journey.secondaryAction!.target)}
                        className="w-full justify-between"
                      >
                        <span>{journey.secondaryAction.label}</span>
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    )}
                  </div>

                  {journey.primaryAction && (
                    <p className="mt-3 text-xs text-muted-foreground">
                      {journey.primaryAction.hint}
                    </p>
                  )}

                  {actionError && (
                    <div className="mt-3 flex items-center gap-2 text-sm text-destructive">
                      <XCircle className="h-4 w-4" />
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
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <ScanEye className="h-12 w-12 mb-3" />
                <p>上传照片后查看分析结果</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* History */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-5 w-5" />
            历史分析记录
            {history.length > 0 && (
              <Badge variant="secondary" className="ml-1">{history.length}</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {historyLoading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              加载中...
            </div>
          ) : history.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <History className="h-10 w-10 mb-2" />
              <p className="text-sm">暂无历史记录，完成一次体型分析后将自动保存</p>
            </div>
          ) : (
            <div className="space-y-3">
              {history.map((record) => {
                const isExpanded = expandedRecord === record.id
                return (
                  <div
                    key={record.id}
                    className="rounded-lg border bg-card transition-colors hover:bg-accent/30"
                  >
                    <button
                      className="flex w-full items-center gap-4 p-4 text-left"
                      onClick={() => setExpandedRecord(isExpanded ? null : record.id)}
                    >
                      {record.image_thumbnail && (
                        <img
                          src={`data:image/jpeg;base64,${record.image_thumbnail}`}
                          alt="缩略图"
                          className="h-14 w-14 rounded-md object-cover shrink-0"
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline" className="text-xs">
                            {bodyTypeLabels[record.result.body_type] || record.result.body_type}
                          </Badge>
                          <Badge variant="secondary" className="text-xs">
                            体脂 {record.result.body_fat_range}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground truncate">
                          {formatDate(record.created_at)}
                        </p>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                      )}
                    </button>

                    {isExpanded && (
                      <div className="border-t px-4 pb-4 pt-3 space-y-3">
                        {/* AI 建议置顶 */}
                        <div className="rounded-md bg-muted/50 p-3">
                          <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
                            {record.result.summary}
                          </p>
                        </div>

                        {/* 优势 & 弱势并排 */}
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <p className="text-xs font-medium mb-1">优势部位</p>
                            <div className="flex flex-wrap gap-1">
                              {record.result.strengths.map((s) => (
                                <Badge key={s} variant="secondary" className="text-xs">{t(s)}</Badge>
                              ))}
                            </div>
                          </div>
                          <div>
                            <p className="text-xs font-medium mb-1">需加强</p>
                            <div className="flex flex-wrap gap-1">
                              {record.result.weak_muscles.map((m) => (
                                <Badge key={m} variant="destructive" className="text-xs">{t(m)}</Badge>
                              ))}
                            </div>
                          </div>
                        </div>

                        {/* 部位评分可折叠 */}
                        {record.result.muscle_scores && Object.keys(record.result.muscle_scores).length > 0 && (
                          <div className="rounded-md border">
                            <button
                              className="flex w-full items-center justify-between p-2.5 text-left hover:bg-accent/30 transition-colors rounded-md"
                              onClick={(e) => {
                                e.stopPropagation()
                                setExpandedHistoryScores(expandedHistoryScores === record.id ? null : record.id)
                              }}
                            >
                              <span className="flex items-center gap-1.5 text-xs font-medium">
                                <BarChart3 className="h-3.5 w-3.5" />
                                部位评分详情
                                <Badge variant="secondary" className="text-[10px] font-normal px-1.5">
                                  {Object.keys(record.result.muscle_scores).length} 项
                                </Badge>
                              </span>
                              {expandedHistoryScores === record.id ? (
                                <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                              )}
                            </button>
                            {expandedHistoryScores === record.id && (
                              <div className="border-t px-2.5 pb-2.5 pt-2 space-y-1.5">
                                {Object.entries(record.result.muscle_scores).map(([part, score]) => (
                                  <div key={part} className="flex items-center gap-2">
                                    <span className="text-xs w-16 shrink-0">{t(part)}</span>
                                    <Progress value={(score as number) * 10} className="flex-1 h-2" />
                                    <span className="text-xs text-muted-foreground w-8 text-right">{score as number}/10</span>
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
        </CardContent>
      </Card>
    </div>
  )
}
