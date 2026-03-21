// derive stable high-fidelity view-models from simple admin APIs; keep CRUD seeds deterministic for prototype mode; verify with vitest
import type {
  AiConfigApi,
  DashboardApi,
  DashboardViewModel,
  RecipeApi,
  RecipeRecord,
  SettingsFormState,
  UserApi,
  UserRecord,
  WorkoutTemplateApi,
} from '../types/admin'

const userPresets = [
  {
    status: '活跃',
    segment: '燃脂会员',
    progressPercent: 58,
    tags: ['高留存', '控卡中'],
    lastActiveLabel: '今天 09:20',
    joinedLabel: '2023-10-24',
    coachName: 'Coach Mia',
    weeklyWorkouts: 5,
    note: '持续执行 16:8 轻断食与力量训练',
  },
  {
    status: '观察',
    segment: '恢复训练',
    progressPercent: 34,
    tags: ['有流失风险', '待回访'],
    lastActiveLabel: '昨天 20:40',
    joinedLabel: '2023-10-22',
    coachName: 'Coach Leo',
    weeklyWorkouts: 2,
    note: '上周有两次计划中断，需要激励提醒',
  },
  {
    status: '高价值',
    segment: '塑形会员',
    progressPercent: 72,
    tags: ['高客单', '训练稳定'],
    lastActiveLabel: '今天 07:10',
    joinedLabel: '2023-10-21',
    coachName: 'Coach Yuki',
    weeklyWorkouts: 6,
    note: '偏好晨练和高蛋白食谱，适合升级训练营',
  },
  {
    status: '休眠',
    segment: '回流用户',
    progressPercent: 18,
    tags: ['待召回', '轻饮食'],
    lastActiveLabel: '3 天前',
    joinedLabel: '2023-10-16',
    coachName: 'Coach Ann',
    weeklyWorkouts: 1,
    note: '适合用低门槛菜谱和短时训练重新激活',
  },
] as const

const recipePresets = [
  {
    category: '燃脂午餐',
    difficulty: '简单',
    durationMinutes: 15,
    scene: '高蛋白控卡',
    imageAccent: 'linear-gradient(135deg, #fdba74 0%, #fb7185 100%)',
    protein: 35,
    carbs: 18,
    fat: 9,
    extraTag: '低油',
    subtitle: '加入柠檬和香料提鲜',
  },
  {
    category: '轻食早餐',
    difficulty: '简单',
    durationMinutes: 10,
    scene: '轻食补水',
    imageAccent: 'linear-gradient(135deg, #7dd3fc 0%, #34d399 100%)',
    protein: 8,
    carbs: 12,
    fat: 5,
    extraTag: '清爽',
    subtitle: '清爽的芽苗配柠汁调味',
  },
  {
    category: '训练后恢复',
    difficulty: '中等',
    durationMinutes: 25,
    scene: '增肌恢复',
    imageAccent: 'linear-gradient(135deg, #c084fc 0%, #fb7185 100%)',
    protein: 28,
    carbs: 30,
    fat: 12,
    extraTag: '高纤',
    subtitle: '香煎三文鱼搭配椰香蔬菜',
  },
  {
    category: '高纤晚餐',
    difficulty: '中等',
    durationMinutes: 45,
    scene: '夜间控卡',
    imageAccent: 'linear-gradient(135deg, #f9a8d4 0%, #f97316 100%)',
    protein: 24,
    carbs: 22,
    fat: 10,
    extraTag: '轻负担',
    subtitle: '香辣肉酱与豆类增加饱腹感',
  },
] as const

const levelLabels: Record<string, string> = {
  beginner: '新手友好',
  intermediate: '进阶燃脂',
  advanced: '高强爆发',
}

export const buildUserRecords = (items: UserApi[]): UserRecord[] =>
  items.map((item, index) => {
    const preset = userPresets[index % userPresets.length]
    const emailPrefix = item.nickname.toLowerCase().replace(/\s+/g, '.')
    return {
      userId: item.user_id,
      nickname: item.nickname,
      email: `${emailPrefix}@fitflow.pro`,
      avatarLabel: item.nickname.slice(0, 2).toUpperCase(),
      currentWeightKg: item.weight_kg,
      goalWeightKg: item.goal_weight_kg,
      status: preset.status,
      segment: preset.segment,
      progressPercent: preset.progressPercent,
      goalLabel: item.goal_weight_kg < item.weight_kg ? '减脂塑形' : '增肌维稳',
      tags: [...preset.tags],
      lastActiveLabel: preset.lastActiveLabel,
      joinedLabel: preset.joinedLabel,
      coachName: preset.coachName,
      weeklyWorkouts: preset.weeklyWorkouts,
      note: preset.note,
    }
  })

export const buildRecipeRecords = (items: RecipeApi[]): RecipeRecord[] =>
  items.map((item, index) => {
    const preset = recipePresets[index % recipePresets.length]
    return {
      recipeId: item.recipe_id,
      name: item.name,
      subtitle: preset.subtitle,
      calories: item.calories,
      category: preset.category,
      difficulty: preset.difficulty,
      durationMinutes: preset.durationMinutes,
      scene: preset.scene,
      imageAccent: preset.imageAccent,
      tags: [item.tag, preset.extraTag],
      nutrition: {
        protein: preset.protein,
        carbs: preset.carbs,
        fat: preset.fat,
      },
      steps: [
        `准备 ${item.name} 的主食材与轻调味料`,
        `按照 ${preset.scene} 目标控制油盐比例与火候`,
        `出锅后按 ${item.tag} 标签做分量摆盘`,
      ],
    }
  })

export const buildSettingsFormState = (
  workoutTemplates: WorkoutTemplateApi[],
  aiConfig: AiConfigApi,
): SettingsFormState => ({
  general: {
    appName: '练了么后台',
    supportEmail: 'support@fitflow.pro',
    logoHint: '正方形 SVG 或 PNG，最大 2MB',
    region: '中国大陆',
  },
  theme: {
    brandHex: '#F21162',
    accentHex: '#FF7A45',
    displayFont: 'DIN Alternate',
    surfaceStyle: 'Soft Light',
  },
  templates: {
    items: workoutTemplates.map((template, index) => ({
      id: template.template_id,
      name: template.name,
      level: template.level,
      levelLabel: levelLabels[template.level] ?? '自定义计划',
      active: index === 0,
      description:
        template.level === 'beginner'
          ? '适合减脂新人，强调动作建立与节奏感。'
          : template.level === 'intermediate'
            ? '提高心肺与力量密度，适合稳定执行用户。'
            : '强化冲刺与周期性挑战，适合高目标人群。',
    })),
  },
  ai: {
    textModel: aiConfig.text_model,
    visionModel: aiConfig.vision_model,
    voiceEnabled: aiConfig.voice_enabled,
    safetyMode: aiConfig.safety_mode,
    modes: [
      { key: 'motivation', title: '激励型', subtitle: '助力冲刺，突破极限', active: true },
      { key: 'companion', title: '共情型', subtitle: '温和陪伴，持续复盘', active: false },
      { key: 'science', title: '科学型', subtitle: '数据驱动，精准严谨', active: false },
    ],
  },
})

export const buildDashboardViewModel = (
  dashboard: DashboardApi,
  users: UserRecord[],
  recipes: RecipeRecord[],
): DashboardViewModel => ({
  heroCards: [
    { key: 'users', label: '总用户数', value: dashboard.users_total.toLocaleString(), deltaLabel: '+12%', icon: 'users' },
    { key: 'active', label: '今日活跃', value: dashboard.daily_active.toLocaleString(), deltaLabel: '+5%', icon: 'pulse' },
    { key: 'workouts', label: '训练总完成', value: dashboard.workouts_total.toLocaleString(), deltaLabel: '+18%', icon: 'dumbbell' },
    {
      key: 'calories',
      label: '累计消耗热量',
      value: `${(dashboard.calories_burned_total / 1000000).toFixed(1)}M`,
      deltaLabel: '+10%',
      icon: 'fire',
    },
  ],
  trend: {
    points: [
      { label: '一月', value: 18 },
      { label: '二月', value: 26 },
      { label: '三月', value: 22 },
      { label: '四月', value: 44 },
      { label: '五月', value: 39 },
      { label: '六月', value: 51 },
    ],
  },
  nutrition: {
    totalCaloriesLabel: '2,450',
    segments: [
      { label: '蛋白质', value: 50, tone: 'brand' },
      { label: '碳水', value: 30, tone: 'accent' },
      { label: '脂肪', value: 20, tone: 'soft' },
    ],
  },
  quickActions: [
    { title: '新增菜谱', description: '快速录入训练期推荐餐单', target: 'recipes' },
    { title: '复盘用户', description: '查看高风险流失用户名单', target: 'users' },
    { title: '调优教练', description: '微调 AI 教练语气和模板', target: 'settings' },
  ],
  recentUsers: users.slice(0, 5),
  recentActivities: [
    {
      id: 'act-1',
      title: `已更新 ${recipes[0]?.name ?? '训练恢复餐单'}`,
      detail: '菜谱热量与标签已同步到前台推荐池',
      module: '菜谱管理',
      timeLabel: '12 分钟前',
    },
    {
      id: 'act-2',
      title: `跟进 ${users[0]?.nickname ?? 'Sarah'} 的训练计划`,
      detail: '已将用户风险状态标记为高优先级回访',
      module: '用户管理',
      timeLabel: '28 分钟前',
    },
    {
      id: 'act-3',
      title: 'AI 教练主题已切换为激励型',
      detail: '系统设置中的对话语气包已完成保存',
      module: '系统设置',
      timeLabel: '1 小时前',
    },
  ],
})
