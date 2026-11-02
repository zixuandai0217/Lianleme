/* Opt-in 3D muscle heatmap panel.
 *
 * The text conclusion and the score list are rendered by the analysis page and
 * stay visible whether this panel is closed, loading, or degraded. This
 * component only adds the WebGL view on top and always renders a readable list
 * as its own fallback — never a blank panel.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import { AlertTriangle, ArrowLeftRight, Info, Loader2, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  HEATMAP_LEGEND_HINT,
  buildHeatmapScene,
  compareHeatmaps,
  capabilityFailureState,
  emptyScoresState,
  modelLoadFailureState,
  type HeatmapScene,
  type MuscleLevel,
  type MuscleRegion,
} from "@/muscle-heatmap"
import {
  annotationForDiff,
  buildAriaSummary,
  createMuscleHeatmapRuntime,
  describeRegion,
  probeHeatmapCapability,
  weakRegionsFromAnalysis,
  type HeatmapRuntime,
  type HeatmapRuntimeInput,
} from "@/lib/muscle-heatmap-3d"
import { cn } from "@/lib/utils"

export interface MuscleHeatmap3DProps {
  scores: Record<string, number> | null | undefined
  compareScores?: Record<string, number> | null
  compareLabel?: string
  currentLabel?: string
  weakMuscles?: readonly string[]
  className?: string
}

type HeatmapStatus = "loading" | "ready" | "unsupported" | "failed"

const LOADING_NOTICE = "正在加载 3D 视图…"

const LEVEL_CLASS: Readonly<Record<MuscleLevel, string>> = {
  偏弱: "bg-destructive/10 text-destructive",
  待加强: "bg-orange-500/10 text-orange-600",
  中等: "bg-muted text-muted-foreground",
  良好: "bg-brand-green/10 text-brand-green",
  优秀: "bg-brand-green/15 text-brand-green",
  未评估: "bg-muted text-muted-foreground",
}

function HeatmapScoreList({ scene }: { scene: HeatmapScene }) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-2" aria-label="部位评分列表">
      {scene.visuals.map((visual) => (
        <div
          key={visual.region}
          className="flex items-center justify-between gap-2 rounded-md bg-background/70 px-2.5 py-1.5 text-xs"
        >
          <span className="text-muted-foreground">{visual.label}</span>
          <span className="flex items-center gap-2">
            {visual.evaluated ? (
              <span className="tabular-nums">{visual.score}/10</span>
            ) : (
              <span className="text-muted-foreground">未评估</span>
            )}
            <span className={cn("rounded-sm px-1.5 py-0.5 text-[0.6rem]", LEVEL_CLASS[visual.level])}>
              {visual.level}
            </span>
          </span>
        </div>
      ))}
      {scene.unmapped.length > 0 && (
        <p className="text-[0.65rem] text-muted-foreground sm:col-span-2">
          另有 {scene.unmapped.length} 个部位（{scene.unmapped.map((item) => item.label).join("、")}）未纳入 3D，仍保留在原始评分列表中。
        </p>
      )}
    </div>
  )
}

function HeatmapLegend() {
  return (
    <div className="rounded-lg border border-border p-3" aria-label="热力图图例">
      <div className="flex items-center gap-2 text-[0.65rem] text-muted-foreground">
        <span>0</span>
        <span
          className="h-2 flex-1 rounded-full"
          style={{ background: "linear-gradient(to right, hsl(0 100% 50%), hsl(60 100% 50%))" }}
        />
        <span>10</span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.65rem] text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="size-2 rounded-full bg-[hsl(0_0%_55%)]" />
          未评估
        </span>
        <span>{HEATMAP_LEGEND_HINT}</span>
      </div>
    </div>
  )
}

export function MuscleHeatmap3D({
  scores,
  compareScores = null,
  compareLabel,
  currentLabel = "本次分析",
  weakMuscles = [],
  className,
}: MuscleHeatmap3DProps) {
  const scene = useMemo(() => buildHeatmapScene(scores), [scores])
  const compareScene = useMemo(
    () => (compareScores ? buildHeatmapScene(compareScores) : null),
    [compareScores],
  )
  const diff = useMemo(
    () => (compareScores ? compareHeatmaps(compareScores, scores) : null),
    [compareScores, scores],
  )
  const weakRegions = useMemo(() => weakRegionsFromAnalysis(weakMuscles), [weakMuscles])
  const topChange = diff?.topChanges[0] ?? null
  const annotation = annotationForDiff(diff)
  const hasScores = scene.hasScores
  const compareEnabled = compareScene !== null

  const [runtimeState, setRuntimeState] = useState<{
    status: Exclude<HeatmapStatus, "unsupported">
    notice: string
  }>({ status: "loading", notice: LOADING_NOTICE })
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState<MuscleRegion | null>(null)

  const containerRef = useRef<HTMLDivElement>(null)
  const runtimeRef = useRef<HeatmapRuntime | null>(null)
  const latestRef = useRef<HeatmapRuntimeInput>({
    scene,
    compareScene,
    highlightRegion: topChange?.region ?? null,
  })

  // Capability is probed before three is imported; a missing/unsupported GPU
  // never loads a runtime or the model.
  const capability = useMemo(
    () => (hasScores ? probeHeatmapCapability() : "unsupported"),
    [hasScores],
  )
  const canRender3d = hasScores && capability === "supported"
  const status: HeatmapStatus = canRender3d ? runtimeState.status : "unsupported"
  const notice = !hasScores
    ? emptyScoresState().notice
    : capability !== "supported"
      ? capabilityFailureState(capability).notice
      : runtimeState.notice

  useEffect(() => {
    latestRef.current = {
      scene,
      compareScene,
      highlightRegion: topChange?.region ?? null,
    }
  }, [scene, compareScene, topChange?.region])

  useEffect(() => {
    const container = containerRef.current
    if (!container || !canRender3d) return

    let cancelled = false
    setRuntimeState({ status: "loading", notice: LOADING_NOTICE })

    createMuscleHeatmapRuntime(container, latestRef.current, {
      onSelect: (region) => {
        if (!cancelled) setSelected(region)
      },
    })
      .then((runtime) => {
        if (cancelled) {
          runtime.dispose()
          return
        }
        runtimeRef.current = runtime
        setRuntimeState({ status: "ready", notice: "" })
      })
      .catch(() => {
        if (cancelled) return
        setRuntimeState({ status: "failed", notice: modelLoadFailureState().notice })
      })

    return () => {
      cancelled = true
      runtimeRef.current?.dispose()
      runtimeRef.current = null
    }
  }, [attempt, canRender3d, compareEnabled])

  useEffect(() => {
    runtimeRef.current?.update(latestRef.current)
  }, [scene, compareScene, topChange?.region])

  useEffect(() => {
    if (status !== "ready") return
    runtimeRef.current?.resize()
  }, [status])

  const retry = () => {
    setSelected(null)
    setRuntimeState({ status: "loading", notice: LOADING_NOTICE })
    setAttempt((current) => current + 1)
  }

  const selectedVisual = selected ? scene.byRegion[selected] : null
  const selectedDetail = selectedVisual
    ? describeRegion(selectedVisual, weakRegions.has(selectedVisual.region))
    : null

  return (
    <section
      className={cn("space-y-3", className)}
      data-muscle-heatmap
      data-heatmap-status={status}
      data-heatmap-compare={compareEnabled ? "true" : "false"}
    >
      {compareEnabled && status === "ready" && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <ArrowLeftRight className="size-3.5" />
            对比视图：{compareLabel ?? "历史分析"} → {currentLabel}（左/上为历史，右/下为本次）
          </span>
          {annotation && (
            <Badge data-heatmap-annotation variant="outline" className="text-[0.6rem]">
              {annotation}
            </Badge>
          )}
        </div>
      )}

      <div className="relative h-[380px] overflow-hidden rounded-lg border border-border bg-[radial-gradient(circle_at_50%_38%,rgba(64,84,110,0.2),rgba(18,20,24,0.05))] sm:h-[440px]">
        <div
          ref={containerRef}
          data-testid="muscle-heatmap-canvas"
          className={cn(
            "absolute inset-0",
            status === "ready" ? "visible" : "invisible pointer-events-none",
          )}
        />

        {status !== "ready" && (
          <div className="relative z-10 flex h-full flex-col justify-center gap-3 overflow-auto p-4">
            {status === "loading" ? (
              <div data-heatmap-loading className="space-y-1">
                <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <Loader2 className="size-4 animate-spin text-primary" />
                  正在加载 3D 视图…
                </p>
                <p className="text-xs text-muted-foreground">
                  文字结论与评分列表已可使用，无需等待模型。
                </p>
              </div>
            ) : (
              <div
                role="status"
                data-heatmap-fallback={status}
                className={cn(
                  "flex items-start gap-2 rounded-lg border p-3",
                  status === "failed"
                    ? "border-destructive/20 bg-destructive/5"
                    : "border-border bg-muted/30",
                )}
              >
                {status === "failed" ? (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
                ) : (
                  <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                )}
                <div className="space-y-0.5">
                  <p className="text-sm font-semibold">
                    {status === "failed" ? "3D 视图暂不可用" : "3D 视图未启用"}
                  </p>
                  <p className="text-xs text-muted-foreground">{notice}</p>
                </div>
              </div>
            )}

            {status === "failed" && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={retry}
              >
                <RefreshCw className="size-4" />
                重试 3D 视图
              </Button>
            )}

            <HeatmapScoreList scene={scene} />
          </div>
        )}
      </div>

      {status === "ready" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div
            aria-live="polite"
            className="rounded-lg border border-border bg-card px-3 py-2.5 text-xs"
            data-heatmap-selection
          >
            {selectedDetail ? (
              <div className="space-y-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold">{selectedDetail.label}</p>
                  <Badge variant="secondary" className="text-[0.6rem]">
                    {selectedDetail.scoreText}
                  </Badge>
                </div>
                {selectedDetail.isWeak && (
                  <Badge variant="destructive" className="text-[0.6rem]">
                    {selectedDetail.weakLabel}
                  </Badge>
                )}
                <p className="text-muted-foreground">{selectedDetail.advice}</p>
                {topChange && topChange.region === selectedDetail.region && (
                  <p className="text-brand-green">
                    较对比记录 {topChange.delta > 0 ? "+" : ""}
                    {topChange.delta} 分
                  </p>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground">
                点击模型上的肌肉区域查看分数、档位与是否弱势肌群。
              </p>
            )}
          </div>

          <HeatmapLegend />
        </div>
      )}

      {status === "ready" && (
        <div className="space-y-1 text-[0.65rem] text-muted-foreground">
          <p>
            拖拽旋转 · 滚轮缩放 · 方向键旋转 · +/- 缩放 · 点击部位查看分数；空白处点击取消选中。
          </p>
          <p>模型为内置通用人体，仅用于展示评分，不含你的照片；渲染只在本机完成。</p>
        </div>
      )}

      <p className="sr-only">{buildAriaSummary(scene)}</p>
    </section>
  )
}

export default MuscleHeatmap3D
