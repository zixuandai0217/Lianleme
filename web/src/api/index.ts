/* API 方法集合：对应后端全部路由 */
import client, { fetchCoachAnimatedTTSPayload, fetchCoachTTSBlob, fetchCoachTTSStatus } from "./client"
import { buildAdminExportSearch, buildAdminUsersSearch, type AdminUsersRequest } from "@/lib/admin-query"
import type {
  AnalyzeResponse,
  AnalyzeResultResponse,
  AnalyzeTaskStatus,
  AnalysisTaskListResponse,
  ApiKeyStatus,
  BodyAnalysisHistoryResponse,
  BodyAnalysisRecordItem,
  ChatHistoryResponse,
  CheckInStats,
  ChatMessage,
  CoachResponse,
  LoginResponse,
  PaginatedUsers,
  AdminStats,
  AdminExportAuditListResponse,
  AdminUserDetailResponse,
  AdminUserDetailSection,
  PlanResponse,
  CurrentPlanLookup,
  TodayWorkout,
  UserResponse,
  UserProfile,
  BodyAnalysisResult,
  WeightRecord,
  WeightTrend,
  WorkoutCompleteRequest,
  WorkoutRecord as WorkoutRecordResp,
  CalendarDay,
  NotificationListResponse,
  WorkoutSessionView,
  MarkAllNotificationsReadResponse,
  MarkNotificationReadResponse,
} from "./types"

// ── Auth ──
export const devLogin = () =>
  client.post<unknown, LoginResponse>("/api/user/dev-login")

export const devAdminLogin = () =>
  client.post<unknown, LoginResponse>("/api/user/dev-login/admin")

export const register = (email: string, password: string, nickname?: string) =>
  client.post<unknown, LoginResponse>("/api/user/register", { email, password, nickname: nickname || "" })

export const emailLogin = (email: string, password: string) =>
  client.post<unknown, LoginResponse>("/api/user/auth/login", { email, password })

// ── User ──
export const getCurrentUser = () =>
  client.get<unknown, UserResponse>("/api/user/me")

export const getUser = (userId: number) =>
  client.get<unknown, UserResponse>(`/api/user/${userId}`)

export const updateProfile = (userId: number, data: { nickname?: string; profile?: Record<string, unknown> }) =>
  client.put<unknown, UserResponse>(`/api/user/${userId}/profile`, data)

export const saveApiKey = (userId: number, provider: string, apiKey: string) =>
  client.post<unknown, ApiKeyStatus>(`/api/user/${userId}/api-key`, { provider, api_key: apiKey })

export const deleteApiKey = (userId: number) =>
  client.delete<unknown, ApiKeyStatus>(`/api/user/${userId}/api-key`)

// ── Vision ──
export const startAnalyze = (userId: number, imageBase64: string, profile?: UserProfile) =>
  client.post<unknown, AnalyzeResponse>("/api/vision/analyze", {
    user_id: userId,
    image_base64: imageBase64,
    profile,
  })

export const getAnalyzeResult = (taskId: string) =>
  client.get<unknown, AnalyzeResultResponse>(`/api/vision/analyze/${taskId}`)

export const getAnalysisHistory = (userId: number, limit = 20) =>
  client.get<unknown, BodyAnalysisHistoryResponse>(`/api/vision/${userId}/history?limit=${limit}`)

/** 任务列表：执行记录级摘要，支持状态过滤与游标分页。 */
export const getAnalysisTasks = (params: {
  status?: AnalyzeTaskStatus
  limit?: number
  cursor?: string | null
} = {}) =>
  client.get<unknown, AnalysisTaskListResponse>("/api/vision/tasks", {
    params: {
      status: params.status,
      limit: params.limit,
      cursor: params.cursor ?? undefined,
    },
  })

export const getAnalysisRecord = (recordId: number) =>
  client.get<unknown, BodyAnalysisRecordItem>(`/api/vision/record/${recordId}`)

// ── Plan ──
export const getCurrentPlan = (userId: number) =>
  client.get<unknown, PlanResponse>(`/api/plan/${userId}/current`)

/**
 * 判断当前用户是否已有可用计划，并保留 HTTP 状态码语义。
 *
 * 与 getCurrentPlan 的区别：404 是「还没有计划」这一正常首用状态，网络失败与 5xx
 * 只能算「无法判别」，绝不降级成 missing。
 *
 * 为什么这里不走 axios 封装：共享封装的响应拦截器把任何失败都压成一句字符串消息，
 * 并丢掉 HTTP 状态码，调用方无法区分「资源不存在」与「网络/服务失败」。而首用引导必须
 * 区分两者——404 可以引导用户去生成计划；请求失败只能算「无法判别」。若误判成没有
 * 计划，用户会被引导去重新生成，而重新生成会归档当前 active 计划。因此这里直接读
 * 状态码；等封装层统一保留状态码后，再收敛回 client。
 */
export async function lookupCurrentPlan(userId: number): Promise<CurrentPlanLookup> {
  const token = localStorage.getItem("token")
  let response: Response

  try {
    response = await fetch(`/api/plan/${userId}/current`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
  } catch {
    return { lookup: "unknown" }
  }

  if (response.status === 404) return { lookup: "missing" }
  if (!response.ok) return { lookup: "unknown" }

  try {
    const payload = (await response.json()) as PlanResponse
    if (!payload?.plan) return { lookup: "unknown" }
    return { lookup: "exists", planId: payload.plan.id }
  } catch {
    return { lookup: "unknown" }
  }
}

export const generatePlan = (
  userId: number,
  bodyAnalysis?: BodyAnalysisResult,
  profile?: UserProfile,
) =>
  client.post<unknown, PlanResponse>("/api/plan/generate", {
    user_id: userId,
    body_analysis: bodyAnalysis,
    profile,
  })

export const getTodayWorkout = (userId: number) =>
  client.get<unknown, TodayWorkout>(`/api/plan/${userId}/today`)

// ── Coach ──
export const chatWithCoach = (msg: ChatMessage) =>
  client.post<unknown, CoachResponse>("/api/coach/chat", msg)

export const getChatHistory = (userId: number, limit = 50) =>
  client.get<unknown, ChatHistoryResponse>(`/api/coach/${userId}/history?limit=${limit}`)

export const getCoachTTSStatus = () => fetchCoachTTSStatus()

export const fetchCoachTTS = (text: string) => fetchCoachTTSBlob(text)

export const fetchCoachAnimatedTTS = (text: string, signal?: AbortSignal) =>
  fetchCoachAnimatedTTSPayload(text, signal)

// ── Workout ──
export const completeWorkout = (req: WorkoutCompleteRequest) =>
  client.post<unknown, WorkoutRecordResp>("/api/workout/complete", req)

export const getCheckinStats = (userId: number) =>
  client.get<unknown, CheckInStats>(`/api/workout/${userId}/stats`)

export const getCalendar = (userId: number, year?: number, month?: number) => {
  const params = new URLSearchParams()
  if (year) params.set("year", String(year))
  if (month) params.set("month", String(month))
  const qs = params.toString()
  return client.get<unknown, CalendarDay[]>(`/api/workout/${userId}/calendar${qs ? `?${qs}` : ""}`)
}

// ── Weight ──
export const addWeightRecord = (userId: number, weight: number, recordedDate?: string, note?: string) =>
  client.post<unknown, WeightRecord>("/api/weight/record", {
    user_id: userId,
    weight,
    recorded_date: recordedDate,
    note,
  })

export const getWeightTrend = (userId: number, days = 90) =>
  client.get<unknown, WeightTrend>(`/api/weight/${userId}/trend?days=${days}`)

export const deleteWeightRecord = (userId: number, recordId: number) =>
  client.delete<unknown, { message: string }>(`/api/weight/${userId}/${recordId}`)

// ── Workout session ──
export const startWorkoutSession = (userId: number) =>
  client.post<unknown, WorkoutSessionView>("/api/workout/sessions/start", { user_id: userId })

export const getCurrentWorkoutSession = (userId: number) =>
  client.get<unknown, WorkoutSessionView>(`/api/workout/sessions/current?user_id=${userId}`)

export const completeSessionSet = (sessionId: string, exerciseIndex: number, setIndex: number) =>
  client.post<unknown, WorkoutSessionView>(`/api/workout/sessions/${sessionId}/sets`, {
    exercise_index: exerciseIndex,
    set_index: setIndex,
  })

export const skipSessionExercise = (sessionId: string, exerciseIndex: number, reason: string) =>
  client.post<unknown, WorkoutSessionView>(`/api/workout/sessions/${sessionId}/skip`, {
    exercise_index: exerciseIndex,
    reason,
  })

// ── Notifications ──
export const getNotifications = (
  userId: number,
  options: { unreadOnly?: boolean; page?: number; pageSize?: number } = {},
) => {
  const params = new URLSearchParams()
  if (options.unreadOnly) params.set("unread_only", "true")
  if (options.page) params.set("page", String(options.page))
  if (options.pageSize) params.set("page_size", String(options.pageSize))
  const qs = params.toString()
  return client.get<unknown, NotificationListResponse>(
    `/api/notifications/${userId}${qs ? `?${qs}` : ""}`,
  )
}

export const markNotificationRead = (userId: number, notificationId: number) =>
  client.post<unknown, MarkNotificationReadResponse>(
    `/api/notifications/${userId}/${notificationId}/read`,
  )

export const markAllNotificationsRead = (userId: number) =>
  client.post<unknown, MarkAllNotificationsReadResponse>(
    `/api/notifications/${userId}/read-all`,
  )

// ── Admin ──
// 管理端身份只来自 token：URL 上拼 user_id 既无效也误导，已按 spec 清理。
export const getAdminStats = () => client.get<unknown, AdminStats>("/api/admin/stats")

/** 用户列表：搜索 / 筛选 / 排序 / 分页全部由 URL 状态解析后交给服务端。 */
export const getAdminUsers = (request: AdminUsersRequest) => {
  const query = buildAdminUsersSearch(request)
  return client.get<unknown, PaginatedUsers>(`/api/admin/users${query ? `?${query}` : ""}`)
}

/** 单个用户的运营详情；只请求需要的分区，便于卡片级加载与失败隔离。 */
export const getAdminUserDetail = (
  userId: number,
  options: {
    sections?: AdminUserDetailSection[]
    page?: number
    page_size?: number
  } = {},
) => {
  const params = new URLSearchParams()
  if (options.sections?.length) params.set("sections", options.sections.join(","))
  if (options.page !== undefined && options.page !== 1) params.set("page", String(options.page))
  if (options.page_size !== undefined) params.set("page_size", String(options.page_size))
  const query = params.toString()
  return client.get<unknown, AdminUserDetailResponse>(
    `/api/admin/users/${userId}${query ? `?${query}` : ""}`,
  )
}

/**
 * 按当前筛选下载 CSV。
 *
 * 导出接口只认 Authorization 头，普通 `<a download>` 带不上 token，因此用 fetch 拿
 * blob 再触发浏览器下载；文件名以服务端 Content-Disposition 为准。
 */
export async function downloadAdminUsersExport(request: AdminUsersRequest): Promise<void> {
  const query = buildAdminExportSearch(request)
  const token = localStorage.getItem("token")
  const response = await fetch(`/api/admin/users/export${query ? `?${query}` : ""}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })

  if (!response.ok) {
    let message = "导出失败，请稍后重试"
    try {
      const detail = (await response.json())?.detail
      if (typeof detail === "string") message = detail
      else if (detail?.message) message = detail.message
    } catch {
      // 非 JSON 错误体：保留通用文案
    }
    throw new Error(message)
  }

  const disposition = response.headers.get("content-disposition") ?? ""
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "users.csv"
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

/** 导出审计（只读，按时间倒序）。 */
export const getAdminExportAudits = (page = 1, pageSize = 20) =>
  client.get<unknown, AdminExportAuditListResponse>(
    `/api/admin/export-audits?page=${page}&page_size=${pageSize}`,
  )

export type * from "./types"
