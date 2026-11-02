/**
 * 陪练协议层：帧解码器 + 轮次归约器（纯函数，与 React 无关）。
 *
 * 事件形状以 coach-stream-protocol spec 第 1 节为唯一来源：
 * `data: <单行 JSON>`，帧之间空行分隔，类型判别在 JSON 的 `type` 上。
 * 解码器负责跨块拼帧、忽略心跳注释行、容忍多帧同块与帧被切断；
 * 归约器只接受当前轮次的帧，把事件序列收敛成气泡正文、教练状态、快捷动作与终结原因。
 */

export const COACH_PROTOCOL_VERSION = 1

/** 清洗后整轮无正文时的兜底文案：与后端 `COACH_FALLBACK_REPLY` 同一句，保证实时与历史回放语气一致。 */
export const EMPTY_COACH_REPLY = "刚才那段我卡了一下，homie，再跟我说一遍，我接着带。"

/** Shown as its own notice when the transport ends before the closing frame. */
export const COACH_TRUNCATED_NOTICE = "连接中断，回复可能不完整。"

const ERROR_FALLBACK_MESSAGE = "教练暂时没接上，稍后再试一次。"

const COACH_STATES = ["guide", "count", "rest", "complete"] as const
const ERROR_CODES = [
  "provider_unavailable",
  "rate_limited",
  "upstream_timeout",
  "internal",
] as const
const FINISH_REASONS = ["complete", "error", "truncated"] as const
const MAX_COACH_ACTIONS = 4

export type CoachStateName = (typeof COACH_STATES)[number]
export type CoachErrorCode = (typeof ERROR_CODES)[number]
export type CoachFinishReason = (typeof FINISH_REASONS)[number]
export type CoachTurnStatus = "idle" | "thinking" | "streaming" | "error" | "aborted"

export interface CoachAction {
  label: string
  prompt: string
}

export interface CoachTurnError {
  code: CoachErrorCode
  message: string
}

export type CoachEvent =
  | { type: "turn_started"; protocol: number; turnId: string; messageId: string }
  | { type: "message_chunk"; text: string }
  | { type: "state"; coachState: CoachStateName }
  | { type: "actions"; actions: CoachAction[] }
  | { type: "error"; code: CoachErrorCode; message: string }
  | { type: "done"; finishReason: CoachFinishReason }

/** Narrow a persisted state string to the four protocol values. */
export function isCoachStateName(value: unknown): value is CoachStateName {
  return asMember(value, COACH_STATES) !== null
}

/**
 * Validate a persisted actions snapshot with the same rules as an `actions` frame.
 * Missing or malformed rows degrade to an empty list so old history never errors.
 */
export function normalizeCoachActions(value: unknown): CoachAction[] {
  return asActions(value) ?? []
}

type UnknownRecord = Record<string, unknown>

// ── 帧解码 ──

export interface CoachFrameDecoder {
  /** Feed one raw transport chunk; returns whatever events completed inside it. */
  push(chunk: string): CoachEvent[]
  /** Flush a trailing frame when the transport ends. */
  end(): CoachEvent[]
}

/** Create a decoder that turns raw SSE text into typed coach events. */
export function createCoachFrameDecoder(): CoachFrameDecoder {
  let buffer = ""
  let dataLines: string[] = []

  const dispatch = (): CoachEvent[] => {
    if (!dataLines.length) return []
    const payload = dataLines.join("\n")
    dataLines = []
    const event = parseCoachEvent(payload)
    return event ? [event] : []
  }

  const consumeLine = (rawLine: string): CoachEvent[] => {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine
    if (line === "") return dispatch()
    if (line.startsWith(":")) return [] // comment / heartbeat
    if (!line.startsWith("data:")) return [] // event:/id:/retry: are unused by this protocol
    const value = line.slice("data:".length)
    dataLines.push(value.startsWith(" ") ? value.slice(1) : value)
    return []
  }

  const drain = (flushPartialLine: boolean): CoachEvent[] => {
    const events: CoachEvent[] = []
    let newlineAt = buffer.indexOf("\n")
    while (newlineAt !== -1) {
      const line = buffer.slice(0, newlineAt)
      buffer = buffer.slice(newlineAt + 1)
      events.push(...consumeLine(line))
      newlineAt = buffer.indexOf("\n")
    }
    if (flushPartialLine && buffer) {
      const line = buffer
      buffer = ""
      events.push(...consumeLine(line))
    }
    return events
  }

  return {
    push(chunk: string): CoachEvent[] {
      if (!chunk) return []
      buffer += chunk
      return drain(false)
    },
    end(): CoachEvent[] {
      const events = drain(true)
      events.push(...dispatch())
      return events
    },
  }
}

/** Parse one frame payload; unknown types and missing fields degrade to null. */
function parseCoachEvent(payload: string): CoachEvent | null {
  const trimmed = payload.trim()
  if (!trimmed) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return null
  }
  if (!isRecord(parsed)) return null

  const type = asString(parsed.type)
  if (type === "turn_started") {
    return {
      type,
      protocol: asNumber(parsed.protocol) ?? COACH_PROTOCOL_VERSION,
      turnId: asString(parsed.turn_id),
      messageId: asString(parsed.message_id),
    }
  }
  if (type === "message_chunk") {
    const text = asString(parsed.text)
    return text ? { type, text } : null
  }
  if (type === "state") {
    const coachState = asMember(parsed.coach_state, COACH_STATES)
    return coachState ? { type, coachState } : null
  }
  if (type === "actions") {
    const actions = asActions(parsed.actions)
    return actions ? { type, actions } : null
  }
  if (type === "error") {
    return {
      type,
      code: asMember(parsed.code, ERROR_CODES) ?? "internal",
      message: asString(parsed.message) || ERROR_FALLBACK_MESSAGE,
    }
  }
  if (type === "done") {
    return { type, finishReason: asMember(parsed.finish_reason, FINISH_REASONS) ?? "truncated" }
  }
  return null // unknown event types are ignored for forward compatibility
}

// ── 轮次归约 ──

export interface CoachTurnState {
  status: CoachTurnStatus
  turnId: string
  started: boolean
  body: string
  coachState: CoachStateName
  actions: CoachAction[]
  finishReason: CoachFinishReason | null
  error: CoachTurnError | null
  /** Turn id whose remaining frames are being discarded as a stale replay. */
  ignoredTurnId: string | null
}

export function createCoachTurnState(): CoachTurnState {
  return {
    status: "idle",
    turnId: "",
    started: false,
    body: "",
    coachState: "guide",
    actions: [],
    finishReason: null,
    error: null,
    ignoredTurnId: null,
  }
}

/** Begin one turn locally, before the first frame arrives. */
export function startCoachTurn(
  state: CoachTurnState = createCoachTurnState(),
): CoachTurnState {
  return {
    ...createCoachTurnState(),
    status: "thinking",
    // The last known coach state and quick actions stay until replaced.
    coachState: state.coachState,
    actions: state.actions,
  }
}

export function applyCoachEvents(
  state: CoachTurnState,
  events: readonly CoachEvent[],
): CoachTurnState {
  return events.reduce(applyCoachEvent, state)
}

/** Fold one protocol event into the turn view. */
export function applyCoachEvent(state: CoachTurnState, event: CoachEvent): CoachTurnState {
  if (state.status === "aborted" || state.finishReason !== null) return state

  if (event.type === "turn_started") {
    if (!state.started || state.turnId === "") {
      return {
        ...state,
        started: true,
        turnId: event.turnId,
        status: "streaming",
        ignoredTurnId: null,
      }
    }
    if (event.turnId === state.turnId) return state
    // A late turn's frames belong to an older turn: drop them, never the bubble.
    return { ...state, ignoredTurnId: event.turnId }
  }

  if (state.ignoredTurnId !== null) {
    // The stale tail ends with its own done; then the current turn may continue.
    return event.type === "done" ? { ...state, ignoredTurnId: null } : state
  }

  switch (event.type) {
    case "message_chunk":
      if (state.error) return state // an error already ended the readable body
      return { ...state, body: state.body + event.text, status: "streaming" }
    case "state":
      return { ...state, coachState: event.coachState }
    case "actions":
      return { ...state, actions: event.actions }
    case "error":
      return { ...state, error: { code: event.code, message: event.message } }
    case "done": {
      const body = state.body.trim()
        ? state.body
        : event.finishReason === "complete"
          ? EMPTY_COACH_REPLY
          : state.body
      return {
        ...state,
        body,
        finishReason: event.finishReason,
        status: event.finishReason === "error" ? "error" : "idle",
        ignoredTurnId: null,
      }
    }
  }
}

/** The transport ended before a done frame arrived: keep the body, mark it truncated. */
export function settleCoachTurn(state: CoachTurnState): CoachTurnState {
  if (state.finishReason !== null || state.status === "aborted") return state
  if (state.error) return { ...state, status: "error", finishReason: "error" }
  // No fallback body here: an empty truncated turn shows the "连接中断" notice
  // instead of an invented coach line or an empty bubble.
  return { ...state, status: "idle", finishReason: "truncated" }
}

/** The user stopped the turn: no error, no announcement, nothing to persist. */
export function abortCoachTurn(state: CoachTurnState): CoachTurnState {
  return { ...state, status: "aborted", finishReason: null, ignoredTurnId: null }
}

/** What the page may show and speak after one turn has settled. */
export interface CoachTurnPresentation {
  /** Coach bubble body; empty means no bubble at all. */
  body: string
  /** Independent notice unit, never part of the bubble. */
  notice: string | null
  noticeKind: "error" | "truncated" | null
  /** Text safe to send to the speech queue; notices are never speakable. */
  speakable: string | null
}

/**
 * Separate the bubble, the notice, and speech for one turn.
 *
 * Error copy and the truncation notice are presentation units of their own: they
 * are never appended to the coach body and never reach the speech queue. A user
 * abort produces no notice at all.
 */
export function coachTurnPresentation(turn: CoachTurnState): CoachTurnPresentation {
  const body = turn.body
  if (turn.status === "aborted") {
    return { body, notice: null, noticeKind: null, speakable: null }
  }
  if (turn.error) {
    return {
      body,
      notice: turn.error.message,
      noticeKind: "error",
      speakable: null,
    }
  }
  if (turn.finishReason === "truncated") {
    return {
      body,
      notice: COACH_TRUNCATED_NOTICE,
      noticeKind: "truncated",
      speakable: body.trim() ? body : null,
    }
  }
  return {
    body,
    notice: null,
    noticeKind: null,
    speakable: body.trim() ? body : null,
  }
}

/** Whether a rejected transport read was an abort rather than a broken connection. */
export function isCoachAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "AbortError"
  )
}

// ── 传输适配（页面用它拿归约结果，解码与归约仍然是纯的） ──

export interface CoachStreamRequest {
  url: string
  body: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
  onUpdate?: (state: CoachTurnState) => void
}

/**
 * Stream one coach turn and resolve with its final reduced state.
 *
 * Every transport read is fed into the frame decoder, so frames may be cut at any
 * byte position. A stream that ends before `done` resolves as truncated.
 */
export async function streamCoachTurn(
  request: CoachStreamRequest,
): Promise<CoachTurnState> {
  const decoder = createCoachFrameDecoder()
  const textDecoder = new TextDecoder()
  let state = startCoachTurn()

  const publish = () => request.onUpdate?.(state)
  const apply = (events: CoachEvent[]) => {
    if (!events.length) return
    state = applyCoachEvents(state, events)
    publish()
  }

  publish()

  const response = await fetch(request.url, {
    method: "POST",
    headers: { ...defaultHeaders(), ...request.headers },
    body: JSON.stringify(request.body),
    signal: request.signal,
  })

  if (!response.ok || !response.body) {
    throw new Error(await describeHttpFailure(response))
  }

  const reader = response.body.getReader()
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      apply(decoder.push(textDecoder.decode(value, { stream: true })))
    }
    apply(decoder.push(textDecoder.decode()))
    apply(decoder.end())
  } catch (error) {
    // A user abort stays an abort; any other transport failure means the
    // connection ended before `done`, so the partial turn settles as truncated.
    if (request.signal?.aborted || isCoachAbortError(error)) {
      throw error
    }
  }

  state = settleCoachTurn(state)
  publish()
  return state
}

function defaultHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const token = typeof localStorage === "undefined" ? null : localStorage.getItem("token")
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function describeHttpFailure(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json()
    if (isRecord(payload)) {
      const detail = payload.detail
      if (typeof detail === "string" && detail.trim()) return detail
      if (isRecord(detail)) {
        const message = asString(detail.message)
        if (message.trim()) return message
      }
    }
  } catch {
    // Not JSON: fall back to the status-based message below.
  }
  return `Stream request failed: ${response.status}`
}

// ── 校验小工具（手写，不引入运行时依赖） ──

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : ""
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function asMember<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : null
}

function asActions(value: unknown): CoachAction[] | null {
  if (!Array.isArray(value)) return null
  const actions: CoachAction[] = []
  for (const item of value) {
    if (!isRecord(item)) continue
    const label = asString(item.label).trim()
    if (!label) continue
    const prompt = asString(item.prompt).trim() || label
    actions.push({ label, prompt })
    if (actions.length === MAX_COACH_ACTIONS) break
  }
  return actions
}
