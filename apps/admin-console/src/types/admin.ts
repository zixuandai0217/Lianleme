// centralize admin-console data contracts; all module view-models and local CRUD state; verify with vitest and vite build
export type AdminModuleKey = 'dashboard' | 'recipes' | 'users' | 'settings'

// centralize local admin auth form and session contracts; admin login shell and storage helpers only; verify with npm --workspace apps/admin-console run test -- adminAuth
export interface AdminLoginDraft {
  account: string
  password: string
  rememberDevice: boolean
}

export interface AdminLoginErrors {
  account?: string
  password?: string
}

export interface AdminSession {
  account: string
  displayName: string
  roleLabel: string
  avatarLabel: string
  loginAt: string
  rememberDevice: boolean
}

export interface DashboardApi {
  users_total: number
  daily_active: number
  workouts_total: number
  calories_burned_total: number
}

export interface UserApi {
  user_id: string
  nickname: string
  weight_kg: number
  goal_weight_kg: number
}

export interface RecipeApi {
  recipe_id: string
  name: string
  calories: number
  tag: string
}

export interface WorkoutTemplateApi {
  template_id: string
  name: string
  level: string
}

export interface AiConfigApi {
  text_model: string
  vision_model: string
  voice_enabled: boolean
  safety_mode: string
}

export interface UserRecord {
  userId: string
  nickname: string
  email: string
  avatarLabel: string
  currentWeightKg: number
  goalWeightKg: number
  status: string
  segment: string
  progressPercent: number
  goalLabel: string
  tags: string[]
  lastActiveLabel: string
  joinedLabel: string
  coachName: string
  weeklyWorkouts: number
  note: string
}

export interface RecipeNutrition {
  protein: number
  carbs: number
  fat: number
}

export interface RecipeRecord {
  recipeId: string
  name: string
  subtitle: string
  calories: number
  category: string
  difficulty: string
  durationMinutes: number
  tags: string[]
  scene: string
  imageAccent: string
  nutrition: RecipeNutrition
  steps: string[]
}

export interface HeroCard {
  key: string
  label: string
  value: string
  deltaLabel: string
  icon: string
}

export interface TrendPoint {
  label: string
  value: number
}

export interface NutritionSegment {
  label: string
  value: number
  tone: string
}

export interface ActivityItem {
  id: string
  title: string
  detail: string
  module: string
  timeLabel: string
}

export interface DashboardViewModel {
  heroCards: HeroCard[]
  trend: {
    points: TrendPoint[]
  }
  nutrition: {
    totalCaloriesLabel: string
    segments: NutritionSegment[]
  }
  quickActions: Array<{
    title: string
    description: string
    target: AdminModuleKey
  }>
  recentUsers: UserRecord[]
  recentActivities: ActivityItem[]
}

export interface TemplatePreset {
  id: string
  name: string
  level: string
  levelLabel: string
  active: boolean
  description: string
}

export interface SettingsFormState {
  general: {
    appName: string
    supportEmail: string
    logoHint: string
    region: string
  }
  theme: {
    brandHex: string
    accentHex: string
    displayFont: string
    surfaceStyle: string
  }
  templates: {
    items: TemplatePreset[]
  }
  ai: {
    textModel: string
    visionModel: string
    voiceEnabled: boolean
    safetyMode: string
    modes: Array<{
      key: string
      title: string
      subtitle: string
      active: boolean
    }>
  }
}

export interface RecipeDraft extends RecipeRecord {
  tagsText: string
  stepsText: string
}

export interface UserDraft extends UserRecord {
  tagsText: string
}

export interface ModalState<T> {
  open: boolean
  mode: 'create' | 'edit'
  draft: T
  error: string
}

export interface UserFilters {
  keyword: string
  status: string
}

export interface RecipeFilters {
  keyword: string
  category: string
  difficulty: string
}

export type FilterState = UserFilters | RecipeFilters
