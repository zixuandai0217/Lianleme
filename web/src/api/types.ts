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
  target_weight?: number
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

export type AnalyzeTaskStatus = "pending" | "processing" | "completed" | "failed" | "expired"

export type AnalyzeTaskStage = "queued" | "vision" | "parse" | "persist" | "done"

/** 服务端稳定错误码；未知码按字符串接纳，前端只展示安全文案。 */
export type AnalyzeTaskErrorCode =
  | "api_key_required"
  | "provider_auth_failed"
  | "provider_rate_limited"
  | "provider_timeout"
  | "output_unparsable"
  | "image_invalid"
  | "storage_unavailable"
  | "retry_exhausted"
  | "task_expired"
  | "internal_error"

export interface AnalyzeTaskError {
  code: AnalyzeTaskErrorCode | string
  message: string
  retryable: boolean
}

export interface AnalyzeResponse {
  task_id: string
  status: AnalyzeTaskStatus
  stage?: AnalyzeTaskStage
  created_at?: string
  expires_at?: string
  /** 服务端建议的轮询间隔（毫秒）；缺失时前端回退到默认间隔。 */
  poll_interval_ms?: number
}

export interface AnalyzeResultResponse {
  task_id: string
  status: AnalyzeTaskStatus
  stage?: AnalyzeTaskStage
  attempt?: number
  progress?: number
  result?: BodyAnalysisResult
  error?: AnalyzeTaskError
  created_at?: string
  updated_at?: string
  expires_at?: string
}

export interface BodyAnalysisRecordItem {
  id: number
  /** @deprecated 旧内联缩略图；新接口固定返回 null，前端优先读 image_url / thumbnail_url。 */
  image_thumbnail?: string | null
  /** 原图短时签名 URL；签发失败时为 null。 */
  image_url?: string | null
  /** 缩略图签名 URL；本阶段固定为 null，由后续工单填充。 */
  thumbnail_url?: string | null
  image_asset_id?: string | null
  thumbnail_asset_id?: string | null
  /** 图片链接签发/读取失败时的降级标记；列表仍可用。 */
  degraded?: boolean
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

/** 计划生成依据：当次体型分析快照 + 生成时的档案快照（旧计划可能全为空）。 */
export interface PlanGenerationBasis {
  body_type?: string | null
  body_fat_range?: string | null
  weak_muscles?: string[] | null
  strengths?: string[] | null
  analysis_summary?: string | null
  captured_at?: string | null
  profile_goal?: string | null
}

export type AdjustmentDirection = "increase" | "decrease" | "keep"

/** 最近一次自动调整的说明（由调整结论记录投影，不复制文本）。 */
export interface PlanAdjustmentExplanation {
  direction: AdjustmentDirection
  trigger: "completion_rate"
  completion_rate: number
  occurred_at: string
  reason: string
}

export interface PlanExplanation {
  generation?: PlanGenerationBasis | null
  latest_adjustment?: PlanAdjustmentExplanation | null
}

export interface PlanResponse {
  plan: TrainingPlan
  message: string
  explanation?: PlanExplanation | null
}

/**
 * 当前周计划的存在性。
 * unknown 表示无法判别（网络失败、5xx、鉴权异常等），调用方不得把它当成「没有计划」——
 * 重新生成计划会归档当前 active 计划，误判的代价由用户承担。
 */
export type PlanLookup = "exists" | "missing" | "unknown"

export interface CurrentPlanLookup {
  lookup: PlanLookup
  planId?: number
}

/** 今日状态稳定枚举；老服务端可能不返回该字段，因此类型上可选。 */
export type TodayWorkoutStatus = "training_day" | "rest_day" | "no_plan"

export interface TodayWorkout {
  status?: TodayWorkoutStatus
  day?: number
  focus?: string
  exercises?: Exercise[]
  estimated_duration?: number
  exercise_count?: number
  total_sets?: number
  plan_id?: number
  is_rest_day?: boolean
  message?: string
}

// ── Workout session ──
export type SessionExerciseStatus = "pending" | "completed" | "skipped"

export interface SessionExercise {
  index: number
  order: number
  name: string
  sets: number
  reps: string
  weight_suggestion: string
  tips: string
  rest_seconds: number
  completed_sets: number
  skipped: boolean
  skip_reason?: string | null
  status: SessionExerciseStatus
  target_set_number?: number | null
}

export interface SessionProgressView {
  completed_sets: number
  total_sets: number
  percent: number
}

export interface WorkoutSessionView {
  session_id: string
  user_id: number
  plan_id?: number | null
  status: string
  session_date: string
  started_at: string
  last_activity_at: string
  progress: SessionProgressView
  exercises: SessionExercise[]
  current_exercise?: SessionExercise | null
  next_exercise?: SessionExercise | null
  finished: boolean
  can_checkin: boolean
}

// ── Notifications ──
/** 站内通知（投递记录的收件箱投影）。 */
export interface NotificationItem {
  id: number
  rule_code: string
  title: string
  body: string
  target_path: string
  created_at: string
  read_at?: string | null
  is_read: boolean
}

export interface NotificationListResponse {
  items: NotificationItem[]
  total: number
  unread_count: number
  page: number
  page_size: number
}

export interface MarkNotificationReadResponse {
  notification_id: number
  read_at: string
  unread_count: number
}

export interface MarkAllNotificationsReadResponse {
  updated: number
  unread_count: number
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

/** 需关注标记：服务端规则计算，可多选筛选，多选为并集。 */
export type AdminUserFlag =
  | "new_no_plan"
  | "planned_no_checkin"
  | "inactive_14d"
  | "never_analyzed"
  | "api_key_missing"

/** 列表排序：固定枚举，不接受任意列名。 */
export type AdminUserSort =
  | "registered_asc"
  | "registered_desc"
  | "last_active_asc"
  | "last_active_desc"

export interface AdminUserItem {
  id: number
  nickname?: string | null
  avatar_url?: string | null
  /** openid 掩码（前 6 后 4），接口层已脱敏，前端不再二次截断。 */
  openid: string
  /** 邮箱掩码（保留首字符与域名）。 */
  email_masked?: string | null
  is_admin: boolean
  has_api_key: boolean
  /** 仅在已配置 Key 时有值。 */
  llm_provider?: string | null
  created_at: string
  has_plan: boolean
  plan_difficulty_factor?: number | null
  total_checkins: number
  checkins_30d: number
  last_checkin_date?: string | null
  /** 最近活跃：业务事件时间最大值（不是登录时间）。 */
  last_active_at: string
  days_since_last_checkin?: number | null
  flags: AdminUserFlag[]
}

export interface PaginatedUsers {
  items: AdminUserItem[]
  total: number
  page: number
  page_size: number
}

/** 详情分区固定枚举，顺序即响应里 sections 的回显顺序。 */
export type AdminUserDetailSection =
  | "profile"
  | "body_analysis"
  | "plan"
  | "checkins"
  | "weights"
  | "timeline"
  | "usage"

export interface AdminBodyAnalysisSummary {
  body_type?: string | null
  body_fat_range?: string | null
  weak_muscles?: string[] | null
  strengths?: string[] | null
  summary?: string | null
  analyzed_at?: string | null
  source?: "analysis_record" | "profile_snapshot" | null
}

export interface AdminPlanDaySummary {
  day: number
  focus: string
  is_rest_day: boolean
  exercise_count: number
  total_sets: number
  estimated_duration: number
}

export interface AdminPlanSection {
  plan_id: number
  week_start: string
  difficulty_factor: number
  status: string
  week_structure: AdminPlanDaySummary[]
  generation?: PlanGenerationBasis | null
  latest_adjustment?: PlanAdjustmentExplanation | null
}

export interface AdminCheckinPoint {
  workout_date: string
  completion_rate: number
  duration_minutes: number
  difficulty_rating?: number | null
}

export interface AdminCheckinsSection {
  window_days: number
  series: AdminCheckinPoint[]
  streak_days: number
  total_checkins: number
  completion_rate_distribution: Record<string, number>
}

export interface AdminWeightPoint {
  recorded_date: string
  weight: number
}

export interface AdminWeightsSection {
  window_days: number
  series: AdminWeightPoint[]
  record_count: number
  records_per_week: number
  latest_weight?: number | null
  last_recorded_date?: string | null
}

export type AdminTimelineEventType =
  | "registered"
  | "first_body_analysis"
  | "latest_body_analysis"
  | "first_plan_generated"
  | "latest_plan_adjustment"
  | "first_checkin"
  | "latest_checkin"
  | "first_weight_record"
  | "latest_weight_record"
  | "latest_chat"

export interface AdminTimelineEvent {
  type: AdminTimelineEventType
  occurred_at: string
  summary: string
  message: string
}

export interface AdminTimelinePage {
  items: AdminTimelineEvent[]
  total: number
  page: number
  page_size: number
}

export interface AdminUsageSection {
  has_api_key: boolean
  llm_provider?: string | null
  chat_message_count: number
  user_message_count: number
  assistant_message_count: number
  last_chat_at?: string | null
}

/**
 * 详情聚合响应：未请求的分区整个键不出现；请求了但数据源为空的分区为 null
 * （checkins / weights / timeline / usage 恒为对象，只是内容为空）。
 */
export interface AdminUserDetailResponse {
  user_id: number
  sections: AdminUserDetailSection[]
  profile?: AdminUserItem | null
  body_analysis?: AdminBodyAnalysisSummary | null
  plan?: AdminPlanSection | null
  checkins?: AdminCheckinsSection | null
  weights?: AdminWeightsSection | null
  timeline?: AdminTimelinePage | null
  usage?: AdminUsageSection | null
}

export type AdminExportOutcome = "success" | "rejected"

export interface AdminExportAuditItem {
  id: number
  operator_id: number
  filter_summary: string
  filter_hash: string
  row_count: number
  outcome: AdminExportOutcome
  rejection_reason?: string | null
  created_at: string
}

export interface AdminExportAuditListResponse {
  items: AdminExportAuditItem[]
  total: number
  page: number
  page_size: number
}
