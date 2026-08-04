/* Backend API 类型定义，与 Pydantic schemas 对应 */

// ── User ──
export interface LoginResponse {
  token: string
  user_id: number
  is_new_user: boolean
}

export interface UserProfile {
  height?: number
  weight?: number
  goal?: string
  experience?: string
  age?: number
  gender?: string
}

export interface ApiKeyStatus {
  has_key: boolean
  provider?: string
  masked_key?: string
}

export interface UserResponse {
  id: number
  openid: string
  nickname?: string
  avatar_url?: string
  profile?: UserProfile
  body_analysis?: BodyAnalysisResult
  is_admin?: boolean
  api_key_status?: ApiKeyStatus
}

// ── Vision ──
export interface BodyAnalysisResult {
  body_type: string
  body_fat_range: string
  weak_muscles: string[]
  strengths: string[]
  muscle_scores: Record<string, number>
  summary: string
}

export interface AnalyzeResponse {
  task_id: string
  status: string
}

export interface AnalyzeResultResponse {
  task_id: string
  status: "processing" | "completed" | "failed"
  result?: BodyAnalysisResult
  error?: string
}

export interface BodyAnalysisRecordItem {
  id: number
  image_thumbnail?: string
  result: BodyAnalysisResult
  created_at?: string
}

export interface BodyAnalysisHistoryResponse {
  records: BodyAnalysisRecordItem[]
  total: number
}

// ── Plan ──
export interface Exercise {
  name: string
  sets: number
  reps: string
  weight_suggestion: string
  tips: string
  rest_seconds: number
}

export interface DailyWorkout {
  day: number
  focus: string
  exercises: Exercise[]
  estimated_duration: number
  is_rest_day: boolean
}

export interface TrainingPlan {
  id?: number
  user_id: number
  week_start: string
  weekly_plan: DailyWorkout[]
  difficulty_factor: number
  status: string
}

export interface PlanResponse {
  plan: TrainingPlan
  message: string
}

export interface TodayWorkout {
  day?: number
  focus?: string
  exercises?: Exercise[]
  estimated_duration?: number
  is_rest_day?: boolean
  message?: string
}

// ── Coach ──
export interface ChatMessage {
  user_id: number
  message: string
  current_exercise?: string
  completed_sets?: number
  total_sets?: number
  plan_id?: number
}

export interface CoachResponse {
  reply: string
  coach_state: string
  suggested_actions: string[]
}

export interface ChatMessageItem {
  id: number
  role: "user" | "assistant"
  content: string
  created_at?: string
}

export interface ChatHistoryResponse {
  messages: ChatMessageItem[]
  total: number
}

export type CoachViseme = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "X"

export interface CoachMouthCue {
  start: number
  end: number
  value: CoachViseme
}

export interface CoachAnimatedTTSResponse {
  audio_base64: string
  mime_type: "audio/wav"
  duration_seconds: number
  mouth_cues: CoachMouthCue[]
  alignment: "rhubarb" | "energy"
}

export interface CoachTTSStatusResponse {
  available: boolean
  lip_sync_available: boolean
}

// ── Workout ──
export interface WorkoutCompleteRequest {
  user_id: number
  plan_id?: number
  workout_date: string
  total_sets: number
  completed_sets: number
  duration_minutes: number
  difficulty_rating?: number
  detail?: Record<string, unknown>
}

export interface WorkoutRecord {
  id: number
  workout_date: string
  completion_rate: number
  duration_minutes: number
  ai_feedback?: string
}

export interface CheckInStats {
  total_checkins: number
  streak_days: number
  monthly_checkins: number
  monthly_completion_rate: number
  recent_records: WorkoutRecord[]
}

export interface CalendarDay {
  date: string
  has_checkin: boolean
  completion_rate?: number
}

// ── Weight ──
export interface WeightRecord {
  id: number
  weight: number
  recorded_date: string
  note?: string
  created_at?: string
}

export interface WeightTrend {
  records: WeightRecord[]
  total: number
  current_weight?: number
  start_weight?: number
  min_weight?: number
  max_weight?: number
  change?: number
}

// ── Admin ──
export interface AdminStats {
  total_users: number
  total_plans: number
  total_workouts: number
  active_users_7d: number
}

export interface AdminUserItem {
  id: number
  openid: string
  nickname?: string
  created_at: string
  has_plan: boolean
  total_checkins: number
}

export interface PaginatedUsers {
  items: AdminUserItem[]
  total: number
  page: number
  page_size: number
}
