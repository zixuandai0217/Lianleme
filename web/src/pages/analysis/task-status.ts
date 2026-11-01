/* 体型分析任务状态收口：五态文案、下一步动作、终止判断与轮询节奏都收敛到纯函数。 */
import type {
  AnalyzeResultResponse,
  AnalyzeTaskError,
  AnalyzeTaskStatus,
  BodyAnalysisResult,
} from "@/api/types"

/** 服务端没有给建议间隔时沿用既有节奏，轮询次数上限仍是最后一道保险。 */
export const DEFAULT_POLL_INTERVAL_MS = 2000
export const MIN_POLL_INTERVAL_MS = 500
export const MAX_POLL_INTERVAL_MS = 15_000
export const MAX_POLL_ATTEMPTS = 60

export type AnalysisTaskActionKind = "restart" | "configure-key" | "generate-plan"

export interface AnalysisTaskAction {
  kind: AnalysisTaskActionKind
  label: string
  hint: string
}

export interface AnalysisTaskView {
  status: AnalyzeTaskStatus
  title: string
  description: string
  primaryAction: AnalysisTaskAction | null
  secondaryAction: AnalysisTaskAction | null
  /** 是否已经不会再变化：页面必须立即停止轮询。 */
  terminal: boolean
  /** 是否提供重新发起入口；失败态由服务端 retryable 决定。 */
  retryable: boolean
  keepPolling: boolean
}

export interface AnalysisTaskSnapshot {
  status: AnalyzeTaskStatus
  error?: AnalyzeTaskError | null
}

const TERMINAL_STATUSES: ReadonlySet<AnalyzeTaskStatus> = new Set([
  "completed",
  "failed",
  "expired",
])

const ERROR_TITLES: Record<string, string> = {
  api_key_required: "还没有配置可用的 API Key",
  provider_auth_failed: "AI 服务鉴权失败",
  provider_rate_limited: "AI 服务此刻繁忙",
  provider_timeout: "AI 分析超时",
  output_unparsable: "分析结果解析失败",
  image_invalid: "照片无法识别",
  storage_unavailable: "分析结果保存失败",
  retry_exhausted: "多次重试后仍未完成分析",
  task_expired: "分析任务已过期",
  internal_error: "分析服务暂时不可用",
}

const ERROR_FALLBACKS: Record<string, string> = {
  api_key_required: "请先在个人资料里配置可用的 API Key，再重新发起分析。",
  provider_auth_failed: "当前 API Key 无法通过 AI 服务鉴权，请检查配置后重试。",
  provider_rate_limited: "AI 服务当前请求较多，请稍后再重新发起分析。",
  provider_timeout: "AI 服务没有及时返回结果，请稍后重新发起分析。",
  output_unparsable: "这次分析结果无法解析，请重新发起一次。",
  image_invalid: "照片无法被识别，请换一张清晰的全身照后重新发起。",
  storage_unavailable: "分析结果暂时无法保存，请稍后重新发起。",
  retry_exhausted: "这次分析已经用尽重试次数，可以重新发起一次。",
  task_expired: "这次任务已超过有效期，没有产生结果。",
  internal_error: "分析服务暂时不可用，请稍后重新发起。",
}

const DEFAULT_FAILED_MESSAGE = "这次分析没有完成，可以重新发起一次。"
const MAX_SAFE_MESSAGE_LENGTH = 200

const restartAction = (): AnalysisTaskAction => ({
  kind: "restart",
  label: "重新发起分析",
  hint: "使用当前照片重新开始一次分析",
})

const configureKeyAction = (): AnalysisTaskAction => ({
  kind: "configure-key",
  label: "检查 API Key",
  hint: "打开个人资料检查 AI 服务配置",
})

/** 只接受一句服务端安全文案；过长或带换行的内容按原始异常处理，降级为固定文案。 */
function safeServerMessage(message: string | undefined): string | null {
  const trimmed = message?.trim()
  if (!trimmed || trimmed.length > MAX_SAFE_MESSAGE_LENGTH || trimmed.includes("\n")) {
    return null
  }
  return trimmed
}

function failedView(error?: AnalyzeTaskError | null): AnalysisTaskView {
  const code = error?.code
  const fallback = (code && ERROR_FALLBACKS[code]) || DEFAULT_FAILED_MESSAGE
  const isKeyProblem = code === "api_key_required" || code === "provider_auth_failed"
  // 重试耗尽本身可能被服务端标成不可重试，但票面要求仍然给用户重新发起的入口。
  const retryable = Boolean(error?.retryable) || code === "retry_exhausted" || code === "task_expired"

  let primaryAction: AnalysisTaskAction | null = null
  if (isKeyProblem) {
    primaryAction = configureKeyAction()
  } else if (retryable) {
    primaryAction = restartAction()
  }

  return {
    status: "failed",
    title: (code && ERROR_TITLES[code]) || "分析没有完成",
    description: safeServerMessage(error?.message) || fallback,
    primaryAction,
    secondaryAction: null,
    terminal: true,
    retryable,
    keepPolling: false,
  }
}

/** 把一个服务端任务状态映射成用户能看到的一句话、下一步动作与轮询决策。 */
export function mapAnalysisTaskStatus(snapshot: AnalysisTaskSnapshot): AnalysisTaskView {
  const { status } = snapshot

  switch (status) {
    case "pending":
      return {
        status,
        title: "已加入分析队列",
        description: "正在等待执行，通常几秒内开始。",
        primaryAction: null,
        secondaryAction: null,
        terminal: false,
        retryable: false,
        keepPolling: true,
      }
    case "processing":
      return {
        status,
        title: "AI 正在分析你的体型",
        description: "正在识别体型与肌群状态，请保持页面开启。",
        primaryAction: null,
        secondaryAction: null,
        terminal: false,
        retryable: false,
        keepPolling: true,
      }
    case "completed":
      return {
        status,
        title: "分析完成",
        description: "结果已经生成，可以继续生成训练计划。",
        primaryAction: {
          kind: "generate-plan",
          label: "生成专属训练计划",
          hint: "把这次分析结果直接转成训练安排",
        },
        secondaryAction: null,
        terminal: true,
        retryable: false,
        keepPolling: false,
      }
    case "failed":
      return failedView(snapshot.error)
    case "expired":
      return {
        status,
        title: "分析任务已过期",
        description: safeServerMessage(snapshot.error?.message) || ERROR_FALLBACKS.task_expired,
        primaryAction: restartAction(),
        secondaryAction: null,
        terminal: true,
        retryable: true,
        keepPolling: false,
      }
  }
}

/** 终止态一律不再轮询；只有等待中的两态需要继续。 */
export function isTerminalTaskStatus(status: AnalyzeTaskStatus): boolean {
  return TERMINAL_STATUSES.has(status)
}

function validFallback(fallbackMs: number): number {
  return Number.isFinite(fallbackMs) && fallbackMs > 0
    ? Math.round(fallbackMs)
    : DEFAULT_POLL_INTERVAL_MS
}

/**
 * 优先采用服务端建议间隔；缺失或非法时沿用当前间隔。
 * 上下限只用于防止服务端异常造成热循环或超长等待。
 */
export function resolvePollIntervalMs(
  suggestedMs: number | null | undefined,
  fallbackMs: number = DEFAULT_POLL_INTERVAL_MS,
): number {
  const fallback = validFallback(fallbackMs)
  if (typeof suggestedMs !== "number" || !Number.isFinite(suggestedMs) || suggestedMs <= 0) {
    return fallback
  }
  return Math.min(Math.max(Math.round(suggestedMs), MIN_POLL_INTERVAL_MS), MAX_POLL_INTERVAL_MS)
}

export type PollAnalysisOutcome = "completed" | "failed" | "expired" | "timeout"

export interface PollAnalysisResult {
  outcome: PollAnalysisOutcome
  /** 最后一次成功拿到的响应；首次请求就失败时为 null。 */
  response: AnalyzeResultResponse | null
  result: BodyAnalysisResult | null
  error: AnalyzeTaskError | null
}

export interface PollAnalysisOptions {
  taskId: string
  fetchStatus: (taskId: string) => Promise<AnalyzeResultResponse>
  /** 创建任务响应里带的建议间隔。 */
  initialIntervalMs?: number
  maxAttempts?: number
  sleep?: (ms: number) => Promise<void>
  onUpdate?: (response: AnalyzeResultResponse) => void
}

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms))

/**
 * 轮询到终态就返回：completed / failed / expired 之后不会再发请求。
 * 次数上限只作为服务端状态迟迟不推进时的最后保险。
 */
export async function pollAnalysisTask(options: PollAnalysisOptions): Promise<PollAnalysisResult> {
  const { taskId, fetchStatus, initialIntervalMs, onUpdate } = options
  const maxAttempts = Math.max(1, Math.floor(options.maxAttempts ?? MAX_POLL_ATTEMPTS))
  const sleep = options.sleep ?? defaultSleep

  const intervalMs = resolvePollIntervalMs(initialIntervalMs)
  let response: AnalyzeResultResponse | null = null

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    response = await fetchStatus(taskId)
    onUpdate?.(response)

    if (response.status === "completed") {
      if (response.result) {
        return { outcome: "completed", response, result: response.result, error: null }
      }
      return {
        outcome: "failed",
        response,
        result: null,
        error: {
          code: "internal_error",
          message: "分析已完成，但结果没有返回，请重新发起。",
          retryable: true,
        },
      }
    }
    if (response.status === "failed") {
      return { outcome: "failed", response, result: null, error: response.error ?? null }
    }
    if (response.status === "expired") {
      return { outcome: "expired", response, result: null, error: response.error ?? null }
    }

    if (attempt < maxAttempts - 1) {
      await sleep(intervalMs)
    }
  }

  return { outcome: "timeout", response, result: null, error: null }
}
