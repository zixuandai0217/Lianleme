// coordinate admin module loading and local prototype CRUD; keep views thin while refresh resets to API seeds; verify with vitest and vite build
import { computed, reactive, ref, watch } from 'vue'

import {
  buildDashboardViewModel,
  buildRecipeRecords,
  buildSettingsFormState,
  buildUserRecords,
} from '../lib/adminState'
import type {
  AdminModuleKey,
  AiConfigApi,
  DashboardApi,
  ModalState,
  RecipeApi,
  RecipeDraft,
  RecipeFilters,
  RecipeRecord,
  SettingsFormState,
  UserApi,
  UserDraft,
  UserFilters,
  UserRecord,
  WorkoutTemplateApi,
} from '../types/admin'

type ModuleStatus = 'idle' | 'loading' | 'ready' | 'error'
type SettingsSection = 'general' | 'theme' | 'templates' | 'ai'
type ConfirmIntent = 'deleteRecipe' | 'deleteRecipes' | 'deleteUser' | 'deleteUsers' | null

interface ListPayload<T> {
  items: T[]
  total?: number
}

const cloneValue = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

const modules = [
  { key: 'dashboard', label: '控制台', icon: 'dashboard' },
  { key: 'recipes', label: '菜谱管理', icon: 'recipes' },
  { key: 'users', label: '用户管理', icon: 'users' },
  { key: 'settings', label: '系统设置', icon: 'settings' },
] as const satisfies ReadonlyArray<{ key: AdminModuleKey; label: string; icon: string }>

const pageMeta: Record<
  AdminModuleKey,
  {
    title: string
    subtitle: string
    searchPlaceholder: string
  }
> = {
  dashboard: {
    title: '数据概览',
    subtitle: '欢迎回来，这是今天的最新动态。',
    searchPlaceholder: '搜索数据分析、用户动态或配置项...',
  },
  recipes: {
    title: '菜谱管理',
    subtitle: '创建、编辑和整理练了么的健康菜谱收藏。',
    searchPlaceholder: '搜索菜谱名称、标签或食材...',
  },
  users: {
    title: '用户管理',
    subtitle: '查看核心会员状态、进度和重点跟进名单。',
    searchPlaceholder: '搜索用户昵称、邮箱或标签...',
  },
  settings: {
    title: '应用配置',
    subtitle: '全局设置、训练模板和 AI 教练偏好统一管理。',
    searchPlaceholder: '搜索应用配置、训练模板或 AI 模式...',
  },
}

const createRecipeDraft = (index: number): RecipeDraft => ({
  recipeId: `r_local_${String(index).padStart(3, '0')}`,
  name: '',
  subtitle: '用一句话描述适用场景',
  calories: 220,
  category: '燃脂午餐',
  difficulty: '简单',
  durationMinutes: 15,
  tags: ['高蛋白', '低油'],
  tagsText: '高蛋白, 低油',
  scene: '训练恢复',
  imageAccent: 'linear-gradient(135deg, #fdba74 0%, #fb7185 100%)',
  nutrition: {
    protein: 24,
    carbs: 18,
    fat: 8,
  },
  steps: ['准备主食材和轻调味料', '控制火候快速烹饪', '按营养目标分装摆盘'],
  stepsText: '准备主食材和轻调味料\n控制火候快速烹饪\n按营养目标分装摆盘',
})

const createUserDraft = (index: number): UserDraft => ({
  userId: `u_local_${String(index).padStart(3, '0')}`,
  nickname: '',
  email: '',
  avatarLabel: 'NU',
  currentWeightKg: 68,
  goalWeightKg: 60,
  status: '活跃',
  segment: '燃脂会员',
  progressPercent: 32,
  goalLabel: '减脂塑形',
  tags: ['新用户'],
  tagsText: '新用户',
  lastActiveLabel: '刚刚创建',
  joinedLabel: new Date().toISOString().slice(0, 10),
  coachName: 'Coach Mia',
  weeklyWorkouts: 3,
  note: '适合从低门槛轻食和基础力量训练开始。',
})

const toRecipeDraft = (record: RecipeRecord): RecipeDraft => ({
  ...cloneValue(record),
  tagsText: record.tags.join(', '),
  stepsText: record.steps.join('\n'),
})

const toUserDraft = (record: UserRecord): UserDraft => ({
  ...cloneValue(record),
  tagsText: record.tags.join(', '),
})

const parseTags = (value: string) =>
  value
    .split(/[,\n，]/)
    .map((item) => item.trim())
    .filter(Boolean)

const parseSteps = (value: string) =>
  value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)

const buildRecipeRecordFromDraft = (draft: RecipeDraft): RecipeRecord => ({
  recipeId: draft.recipeId,
  name: draft.name.trim(),
  subtitle: draft.subtitle.trim(),
  calories: Number(draft.calories),
  category: draft.category,
  difficulty: draft.difficulty,
  durationMinutes: Number(draft.durationMinutes),
  tags: parseTags(draft.tagsText),
  scene: draft.scene.trim(),
  imageAccent: draft.imageAccent,
  nutrition: {
    protein: Number(draft.nutrition.protein),
    carbs: Number(draft.nutrition.carbs),
    fat: Number(draft.nutrition.fat),
  },
  steps: parseSteps(draft.stepsText),
})

const buildUserRecordFromDraft = (draft: UserDraft): UserRecord => ({
  userId: draft.userId,
  nickname: draft.nickname.trim(),
  email: draft.email.trim(),
  avatarLabel: draft.nickname.trim().slice(0, 2).toUpperCase() || 'NU',
  currentWeightKg: Number(draft.currentWeightKg),
  goalWeightKg: Number(draft.goalWeightKg),
  status: draft.status,
  segment: draft.segment,
  progressPercent: draft.progressPercent,
  goalLabel: draft.goalLabel,
  tags: parseTags(draft.tagsText),
  lastActiveLabel: draft.lastActiveLabel,
  joinedLabel: draft.joinedLabel,
  coachName: draft.coachName.trim(),
  weeklyWorkouts: Number(draft.weeklyWorkouts),
  note: draft.note.trim(),
})

const ensureEmail = (draft: UserDraft) => {
  if (draft.email.trim()) {
    return draft.email.trim()
  }

  const alias = draft.nickname.trim().toLowerCase().replace(/\s+/g, '.')
  return `${alias || 'new.user'}@fitflow.pro`
}

const fetchJson = async <T>(path: string): Promise<T> => {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export const useAdminConsole = () => {
  const activeModule = ref<AdminModuleKey>('dashboard')
  const moduleStatus = reactive<Record<AdminModuleKey, ModuleStatus>>({
    dashboard: 'idle',
    recipes: 'idle',
    users: 'idle',
    settings: 'idle',
  })
  const moduleErrors = reactive<Record<AdminModuleKey, string>>({
    dashboard: '',
    recipes: '',
    users: '',
    settings: '',
  })

  const dashboardApi = ref<DashboardApi | null>(null)
  const dashboardModel = ref<ReturnType<typeof buildDashboardViewModel> | null>(null)
  const users = ref<UserRecord[]>([])
  const recipes = ref<RecipeRecord[]>([])
  const settingsState = ref<SettingsFormState | null>(null)
  const initialSettingsState = ref<SettingsFormState | null>(null)

  const dashboardSearch = ref('')
  const recipeFilters = reactive<RecipeFilters>({
    keyword: '',
    category: '全部',
    difficulty: '全部',
  })
  const userFilters = reactive<UserFilters>({
    keyword: '',
    status: '全部',
  })
  const settingsSearch = ref('')

  const recipePage = ref(1)
  const userPage = ref(1)
  const pageSize = 4

  const selectedRecipeIds = ref<string[]>([])
  const selectedUserIds = ref<string[]>([])

  const recipeModal = reactive<ModalState<RecipeDraft>>({
    open: false,
    mode: 'create',
    draft: createRecipeDraft(1),
    error: '',
  })
  const userModal = reactive<ModalState<UserDraft>>({
    open: false,
    mode: 'create',
    draft: createUserDraft(1),
    error: '',
  })

  const previewRecipeId = ref<string | null>(null)
  const previewUserId = ref<string | null>(null)
  const settingsSection = ref<SettingsSection>('general')
  const saveFeedback = ref('')

  const confirmDialog = reactive({
    open: false,
    title: '',
    description: '',
    actionLabel: '删除',
    intent: null as ConfirmIntent,
    targetIds: [] as string[],
  })

  const toast = reactive({
    visible: false,
    message: '',
  })
  let toastTimer: ReturnType<typeof window.setTimeout> | null = null

  const showToast = (message: string) => {
    toast.visible = true
    toast.message = message
    if (toastTimer) {
      window.clearTimeout(toastTimer)
    }
    toastTimer = window.setTimeout(() => {
      toast.visible = false
      toast.message = ''
    }, 2200)
  }

  const rebuildDashboard = () => {
    if (!dashboardApi.value) {
      return
    }
    dashboardModel.value = buildDashboardViewModel(dashboardApi.value, users.value, recipes.value)
  }

  const loadDashboard = async (force = false) => {
    if (!force && moduleStatus.dashboard === 'ready' && dashboardModel.value) {
      return
    }

    moduleStatus.dashboard = 'loading'
    moduleErrors.dashboard = ''

    try {
      const [dashboardResponse, userResponse, recipeResponse] = await Promise.all([
        fetchJson<DashboardApi>('/v1/admin/dashboard'),
        fetchJson<ListPayload<UserApi>>('/v1/admin/users'),
        fetchJson<ListPayload<RecipeApi>>('/v1/admin/recipes'),
      ])

      dashboardApi.value = dashboardResponse
      users.value = buildUserRecords(userResponse.items)
      recipes.value = buildRecipeRecords(recipeResponse.items)
      moduleStatus.users = 'ready'
      moduleStatus.recipes = 'ready'
      moduleErrors.users = ''
      moduleErrors.recipes = ''
      rebuildDashboard()
      moduleStatus.dashboard = 'ready'
    } catch (error) {
      moduleStatus.dashboard = 'error'
      moduleErrors.dashboard = `加载控制台失败：${error instanceof Error ? error.message : 'unknown error'}`
    }
  }

  const loadUsers = async (force = false) => {
    if (!force && moduleStatus.users === 'ready' && users.value.length) {
      return
    }

    moduleStatus.users = 'loading'
    moduleErrors.users = ''

    try {
      const response = await fetchJson<ListPayload<UserApi>>('/v1/admin/users')
      users.value = buildUserRecords(response.items)
      moduleStatus.users = 'ready'
      rebuildDashboard()
    } catch (error) {
      moduleStatus.users = 'error'
      moduleErrors.users = `加载用户管理失败：${error instanceof Error ? error.message : 'unknown error'}`
    }
  }

  const loadRecipes = async (force = false) => {
    if (!force && moduleStatus.recipes === 'ready' && recipes.value.length) {
      return
    }

    moduleStatus.recipes = 'loading'
    moduleErrors.recipes = ''

    try {
      const response = await fetchJson<ListPayload<RecipeApi>>('/v1/admin/recipes')
      recipes.value = buildRecipeRecords(response.items)
      moduleStatus.recipes = 'ready'
      rebuildDashboard()
    } catch (error) {
      moduleStatus.recipes = 'error'
      moduleErrors.recipes = `加载菜谱管理失败：${error instanceof Error ? error.message : 'unknown error'}`
    }
  }

  const loadSettings = async (force = false) => {
    if (!force && moduleStatus.settings === 'ready' && settingsState.value) {
      return
    }

    moduleStatus.settings = 'loading'
    moduleErrors.settings = ''

    try {
      const [workoutTemplates, aiConfig] = await Promise.all([
        fetchJson<ListPayload<WorkoutTemplateApi>>('/v1/admin/workout-templates'),
        fetchJson<AiConfigApi>('/v1/admin/ai-config'),
      ])
      const nextSettings = buildSettingsFormState(workoutTemplates.items, aiConfig)
      settingsState.value = nextSettings
      initialSettingsState.value = cloneValue(nextSettings)
      moduleStatus.settings = 'ready'
    } catch (error) {
      moduleStatus.settings = 'error'
      moduleErrors.settings = `加载系统设置失败：${error instanceof Error ? error.message : 'unknown error'}`
    }
  }

  const ensureModule = async (module: AdminModuleKey, force = false) => {
    if (module === 'dashboard') {
      await loadDashboard(force)
      return
    }
    if (module === 'recipes') {
      await loadRecipes(force)
      return
    }
    if (module === 'users') {
      await loadUsers(force)
      return
    }
    await loadSettings(force)
  }

  const setActiveModule = async (module: AdminModuleKey) => {
    activeModule.value = module
    await ensureModule(module)
  }

  const refreshActiveModule = async () => {
    await ensureModule(activeModule.value, true)
    if (activeModule.value === 'settings') {
      saveFeedback.value = ''
    } else {
      showToast(`${pageMeta[activeModule.value].title} 已从接口刷新`)
    }
  }

  watch(
    activeModule,
    (module) => {
      void ensureModule(module)
    },
    { immediate: true },
  )

  const activeSearch = computed({
    get: () => {
      if (activeModule.value === 'recipes') {
        return recipeFilters.keyword
      }
      if (activeModule.value === 'users') {
        return userFilters.keyword
      }
      if (activeModule.value === 'settings') {
        return settingsSearch.value
      }
      return dashboardSearch.value
    },
    set: (value: string) => {
      if (activeModule.value === 'recipes') {
        recipeFilters.keyword = value
        return
      }
      if (activeModule.value === 'users') {
        userFilters.keyword = value
        return
      }
      if (activeModule.value === 'settings') {
        settingsSearch.value = value
        return
      }
      dashboardSearch.value = value
    },
  })

  const currentStatus = computed(() => moduleStatus[activeModule.value])
  const currentError = computed(() => moduleErrors[activeModule.value])
  const searchPlaceholder = computed(() => pageMeta[activeModule.value].searchPlaceholder)

  const filteredRecipes = computed(() => {
    const keyword = recipeFilters.keyword.trim().toLowerCase()

    return recipes.value.filter((record) => {
      const matchesKeyword =
        !keyword ||
        [record.name, record.subtitle, record.scene, record.tags.join(' '), record.category]
          .join(' ')
          .toLowerCase()
          .includes(keyword)
      const matchesCategory = recipeFilters.category === '全部' || record.category === recipeFilters.category
      const matchesDifficulty = recipeFilters.difficulty === '全部' || record.difficulty === recipeFilters.difficulty
      return matchesKeyword && matchesCategory && matchesDifficulty
    })
  })

  const filteredUsers = computed(() => {
    const keyword = userFilters.keyword.trim().toLowerCase()

    return users.value.filter((record) => {
      const matchesKeyword =
        !keyword ||
        [record.nickname, record.email, record.tags.join(' '), record.segment].join(' ').toLowerCase().includes(keyword)
      const matchesStatus = userFilters.status === '全部' || record.status === userFilters.status
      return matchesKeyword && matchesStatus
    })
  })

  const recipePageCount = computed(() => Math.max(1, Math.ceil(filteredRecipes.value.length / pageSize)))
  const userPageCount = computed(() => Math.max(1, Math.ceil(filteredUsers.value.length / pageSize)))

  watch(
    () => [recipeFilters.keyword, recipeFilters.category, recipeFilters.difficulty],
    () => {
      recipePage.value = 1
    },
  )

  watch(
    () => [userFilters.keyword, userFilters.status],
    () => {
      userPage.value = 1
    },
  )

  watch(filteredRecipes, () => {
    if (recipePage.value > recipePageCount.value) {
      recipePage.value = recipePageCount.value
    }
  })

  watch(filteredUsers, () => {
    if (userPage.value > userPageCount.value) {
      userPage.value = userPageCount.value
    }
  })

  const paginatedRecipes = computed(() => {
    const start = (recipePage.value - 1) * pageSize
    return filteredRecipes.value.slice(start, start + pageSize)
  })

  const paginatedUsers = computed(() => {
    const start = (userPage.value - 1) * pageSize
    return filteredUsers.value.slice(start, start + pageSize)
  })

  const recipeCategoryOptions = computed(() => ['全部', ...new Set(recipes.value.map((record) => record.category))])
  const recipeDifficultyOptions = computed(() => ['全部', ...new Set(recipes.value.map((record) => record.difficulty))])
  const userStatusOptions = computed(() => ['全部', ...new Set(users.value.map((record) => record.status))])

  const recipeSummaryCards = computed(() => [
    { label: '全部菜谱', value: String(recipes.value.length) },
    { label: '高蛋白', value: String(recipes.value.filter((record) => record.tags.includes('高蛋白')).length) },
    { label: '简单难度', value: String(recipes.value.filter((record) => record.difficulty === '简单').length) },
  ])

  const userSummaryCards = computed(() => [
    { label: '用户总数', value: String(users.value.length) },
    { label: '活跃状态', value: String(users.value.filter((record) => record.status === '活跃').length) },
    { label: '高价值', value: String(users.value.filter((record) => record.status === '高价值').length) },
  ])

  const allVisibleRecipesSelected = computed(
    () =>
      paginatedRecipes.value.length > 0 &&
      paginatedRecipes.value.every((record) => selectedRecipeIds.value.includes(record.recipeId)),
  )

  const allVisibleUsersSelected = computed(
    () => paginatedUsers.value.length > 0 && paginatedUsers.value.every((record) => selectedUserIds.value.includes(record.userId)),
  )

  const previewRecipe = computed(() => recipes.value.find((record) => record.recipeId === previewRecipeId.value) ?? null)
  const previewUser = computed(() => users.value.find((record) => record.userId === previewUserId.value) ?? null)

  const openRecipeCreate = () => {
    recipeModal.mode = 'create'
    recipeModal.open = true
    recipeModal.error = ''
    recipeModal.draft = createRecipeDraft(recipes.value.length + 1)
  }

  const openRecipeEdit = (recipeId: string) => {
    const record = recipes.value.find((item) => item.recipeId === recipeId)
    if (!record) {
      return
    }
    recipeModal.mode = 'edit'
    recipeModal.open = true
    recipeModal.error = ''
    recipeModal.draft = toRecipeDraft(record)
  }

  const saveRecipe = () => {
    if (!recipeModal.draft.name.trim()) {
      recipeModal.error = '请输入菜谱名称'
      return
    }
    if (parseTags(recipeModal.draft.tagsText).length === 0) {
      recipeModal.error = '至少添加一个菜谱标签'
      return
    }
    if (parseSteps(recipeModal.draft.stepsText).length < 2) {
      recipeModal.error = '至少补充两步制作说明'
      return
    }

    const nextRecord = buildRecipeRecordFromDraft(recipeModal.draft)
    const targetIndex = recipes.value.findIndex((record) => record.recipeId === nextRecord.recipeId)

    if (targetIndex >= 0) {
      recipes.value.splice(targetIndex, 1, nextRecord)
      showToast(`已更新菜谱「${nextRecord.name}」`)
    } else {
      recipes.value.unshift(nextRecord)
      showToast(`已创建菜谱「${nextRecord.name}」`)
    }

    recipeModal.open = false
    recipeModal.error = ''
    rebuildDashboard()
  }

  const openDeleteRecipe = (recipeId: string) => {
    confirmDialog.open = true
    confirmDialog.title = '删除菜谱'
    confirmDialog.description = '删除后仅影响当前会话原型，刷新后会恢复接口种子数据。'
    confirmDialog.actionLabel = '确认删除'
    confirmDialog.intent = 'deleteRecipe'
    confirmDialog.targetIds = [recipeId]
  }

  const openDeleteRecipes = () => {
    confirmDialog.open = true
    confirmDialog.title = '批量删除菜谱'
    confirmDialog.description = `即将删除 ${selectedRecipeIds.value.length} 条菜谱记录。`
    confirmDialog.actionLabel = '批量删除'
    confirmDialog.intent = 'deleteRecipes'
    confirmDialog.targetIds = [...selectedRecipeIds.value]
  }

  const openUserCreate = () => {
    userModal.mode = 'create'
    userModal.open = true
    userModal.error = ''
    userModal.draft = createUserDraft(users.value.length + 1)
  }

  const openUserEdit = (userId: string) => {
    const record = users.value.find((item) => item.userId === userId)
    if (!record) {
      return
    }
    userModal.mode = 'edit'
    userModal.open = true
    userModal.error = ''
    userModal.draft = toUserDraft(record)
  }

  const saveUser = () => {
    if (!userModal.draft.nickname.trim()) {
      userModal.error = '请输入用户昵称'
      return
    }

    userModal.draft.email = ensureEmail(userModal.draft)

    if (!userModal.draft.email.includes('@')) {
      userModal.error = '请输入有效邮箱地址'
      return
    }

    const nextRecord = buildUserRecordFromDraft(userModal.draft)
    const targetIndex = users.value.findIndex((record) => record.userId === nextRecord.userId)

    if (targetIndex >= 0) {
      users.value.splice(targetIndex, 1, nextRecord)
      showToast(`已更新用户「${nextRecord.nickname}」`)
    } else {
      users.value.unshift(nextRecord)
      showToast(`已创建用户「${nextRecord.nickname}」`)
    }

    userModal.open = false
    userModal.error = ''
    rebuildDashboard()
  }

  const toggleUserStatus = (userId: string) => {
    const record = users.value.find((item) => item.userId === userId)
    if (!record) {
      return
    }
    record.status = record.status === '休眠' ? '活跃' : '观察'
    showToast(`已更新 ${record.nickname} 的状态`)
    rebuildDashboard()
  }

  const openDeleteUser = (userId: string) => {
    confirmDialog.open = true
    confirmDialog.title = '删除用户'
    confirmDialog.description = '该操作仅作用于当前控制台会话，适合演示完整 CRUD 交互。'
    confirmDialog.actionLabel = '确认删除'
    confirmDialog.intent = 'deleteUser'
    confirmDialog.targetIds = [userId]
  }

  const openDeleteUsers = () => {
    confirmDialog.open = true
    confirmDialog.title = '批量删除用户'
    confirmDialog.description = `即将删除 ${selectedUserIds.value.length} 位用户。`
    confirmDialog.actionLabel = '批量删除'
    confirmDialog.intent = 'deleteUsers'
    confirmDialog.targetIds = [...selectedUserIds.value]
  }

  const closeConfirmDialog = () => {
    confirmDialog.open = false
    confirmDialog.intent = null
    confirmDialog.targetIds = []
  }

  const confirmDestructiveAction = () => {
    if (confirmDialog.intent === 'deleteRecipe' || confirmDialog.intent === 'deleteRecipes') {
      recipes.value = recipes.value.filter((record) => !confirmDialog.targetIds.includes(record.recipeId))
      selectedRecipeIds.value = selectedRecipeIds.value.filter((id) => !confirmDialog.targetIds.includes(id))
      if (previewRecipeId.value && confirmDialog.targetIds.includes(previewRecipeId.value)) {
        previewRecipeId.value = null
      }
      showToast('菜谱记录已删除')
      rebuildDashboard()
    }

    if (confirmDialog.intent === 'deleteUser' || confirmDialog.intent === 'deleteUsers') {
      users.value = users.value.filter((record) => !confirmDialog.targetIds.includes(record.userId))
      selectedUserIds.value = selectedUserIds.value.filter((id) => !confirmDialog.targetIds.includes(id))
      if (previewUserId.value && confirmDialog.targetIds.includes(previewUserId.value)) {
        previewUserId.value = null
      }
      showToast('用户记录已删除')
      rebuildDashboard()
    }

    closeConfirmDialog()
  }

  const toggleRecipeSelection = (recipeId: string) => {
    selectedRecipeIds.value = selectedRecipeIds.value.includes(recipeId)
      ? selectedRecipeIds.value.filter((id) => id !== recipeId)
      : [...selectedRecipeIds.value, recipeId]
  }

  const toggleUserSelection = (userId: string) => {
    selectedUserIds.value = selectedUserIds.value.includes(userId)
      ? selectedUserIds.value.filter((id) => id !== userId)
      : [...selectedUserIds.value, userId]
  }

  const toggleSelectAllRecipes = () => {
    const visibleIds = paginatedRecipes.value.map((record) => record.recipeId)
    if (allVisibleRecipesSelected.value) {
      selectedRecipeIds.value = selectedRecipeIds.value.filter((id) => !visibleIds.includes(id))
      return
    }
    selectedRecipeIds.value = [...new Set([...selectedRecipeIds.value, ...visibleIds])]
  }

  const toggleSelectAllUsers = () => {
    const visibleIds = paginatedUsers.value.map((record) => record.userId)
    if (allVisibleUsersSelected.value) {
      selectedUserIds.value = selectedUserIds.value.filter((id) => !visibleIds.includes(id))
      return
    }
    selectedUserIds.value = [...new Set([...selectedUserIds.value, ...visibleIds])]
  }

  const settingsDirty = computed(
    () =>
      Boolean(settingsState.value && initialSettingsState.value) &&
      JSON.stringify(settingsState.value) !== JSON.stringify(initialSettingsState.value),
  )

  const saveSettings = () => {
    if (!settingsState.value) {
      return
    }
    if (!settingsState.value.general.appName.trim()) {
      showToast('应用名称不能为空')
      return
    }
    if (!settingsState.value.general.supportEmail.includes('@')) {
      showToast('请输入有效的支持邮箱')
      return
    }

    initialSettingsState.value = cloneValue(settingsState.value)
    saveFeedback.value = '刚刚保存'
    showToast('系统设置已保存')
  }

  const resetSettings = () => {
    if (!initialSettingsState.value) {
      return
    }
    settingsState.value = cloneValue(initialSettingsState.value)
    saveFeedback.value = ''
    showToast('已恢复到最近一次保存状态')
  }

  const changeRecipePage = (nextPage: number) => {
    recipePage.value = Math.min(recipePageCount.value, Math.max(1, nextPage))
  }

  const changeUserPage = (nextPage: number) => {
    userPage.value = Math.min(userPageCount.value, Math.max(1, nextPage))
  }

  return {
    modules,
    pageMeta,
    activeModule,
    activeSearch,
    searchPlaceholder,
    currentStatus,
    currentError,
    moduleStatus,
    toast,
    confirmDialog,
    pageSize,
    saveFeedback,
    dashboardSearch,
    dashboardModel,
    recipes,
    users,
    settingsSection,
    settingsState,
    settingsDirty,
    recipeFilters,
    userFilters,
    settingsSearch,
    recipeSummaryCards,
    userSummaryCards,
    recipeCategoryOptions,
    recipeDifficultyOptions,
    userStatusOptions,
    recipePage,
    userPage,
    recipePageCount,
    userPageCount,
    paginatedRecipes,
    paginatedUsers,
    selectedRecipeIds,
    selectedUserIds,
    allVisibleRecipesSelected,
    allVisibleUsersSelected,
    recipeModal,
    userModal,
    previewRecipeId,
    previewUserId,
    previewRecipe,
    previewUser,
    setActiveModule,
    refreshActiveModule,
    openRecipeCreate,
    openRecipeEdit,
    saveRecipe,
    openDeleteRecipe,
    openDeleteRecipes,
    openUserCreate,
    openUserEdit,
    saveUser,
    toggleUserStatus,
    openDeleteUser,
    openDeleteUsers,
    closeConfirmDialog,
    confirmDestructiveAction,
    toggleRecipeSelection,
    toggleUserSelection,
    toggleSelectAllRecipes,
    toggleSelectAllUsers,
    changeRecipePage,
    changeUserPage,
    saveSettings,
    resetSettings,
  }
}
