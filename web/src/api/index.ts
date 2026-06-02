/* API 方法集合：对应后端全部路由 */
import client from "./client"
import type {
  AnalyzeResponse,
  AnalyzeResultResponse,
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
  PlanResponse,
  TodayWorkout,
  UserResponse,
  WeightRecord,
  WeightTrend,
  WorkoutCompleteRequest,
  WorkoutRecord as WorkoutRecordResp,
  CalendarDay,
} from "./types"

// ── Auth ──
export const devLogin = () =>
  client.post<unknown, LoginResponse>("/api/user/dev-login")

export const devAdminLogin = () =>
  client.post<unknown, LoginResponse>("/api/user/dev-login/admin")

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
export const startAnalyze = (userId: number, imageBase64: string, profile?: Record<string, unknown>) =>
  client.post<unknown, AnalyzeResponse>("/api/vision/analyze", {
    user_id: userId,
    image_base64: imageBase64,
    profile,
  })

export const getAnalyzeResult = (taskId: string) =>
  client.get<unknown, AnalyzeResultResponse>(`/api/vision/analyze/${taskId}`)

export const getAnalysisHistory = (userId: number, limit = 20) =>
  client.get<unknown, BodyAnalysisHistoryResponse>(`/api/vision/${userId}/history?limit=${limit}`)

export const getAnalysisRecord = (recordId: number) =>
  client.get<unknown, BodyAnalysisRecordItem>(`/api/vision/record/${recordId}`)

// ── Plan ──
export const getCurrentPlan = (userId: number) =>
  client.get<unknown, PlanResponse>(`/api/plan/${userId}/current`)

export const generatePlan = (userId: number, bodyAnalysis?: Record<string, unknown>, profile?: Record<string, unknown>) =>
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

// ── Admin ──
export const getAdminStats = (userId: number) =>
  client.get<unknown, AdminStats>(`/api/admin/stats?user_id=${userId}`)

export const getAdminUsers = (userId: number, page = 1, pageSize = 20) =>
  client.get<unknown, PaginatedUsers>(`/api/admin/users?user_id=${userId}&page=${page}&page_size=${pageSize}`)

export type * from "./types"
