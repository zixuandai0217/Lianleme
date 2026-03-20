const fallbackMacroGoals = {
  protein: 130,
  carb: 180,
  fat: 70,
  water: 2.0,
}

const fallbackMealTemplates = {
  breakfast: {
    key: 'breakfast',
    period: '早餐',
    title: '牛油果鸡蛋酸奶碗',
    description: '演示示例 · 高蛋白开场，补足上午专注力',
    calories: 368,
    badge: '演示示例',
    ctaLabel: '记录早餐',
    tone: 'tone-breakfast',
  },
  lunch: {
    key: 'lunch',
    period: '午餐',
    title: '香煎鸡胸藜麦能量碗',
    description: '演示示例 · 复合碳水和饱腹感一起补齐',
    calories: 526,
    badge: '演示示例',
    ctaLabel: '记录午餐',
    tone: 'tone-lunch',
  },
  dinner: {
    key: 'dinner',
    period: '晚餐',
    title: '柠香虾仁时蔬意面',
    description: '演示示例 · 晚上更轻盈，也保留满足感',
    calories: 412,
    badge: '演示示例',
    ctaLabel: '记录晚餐',
    tone: 'tone-dinner',
  },
}

export const fallbackDietHomePayload = {
  calorie_target: 2000,
  calorie_consumed: 1306,
  macro: { protein: 118, carb: 156, fat: 52 },
  records: [],
}

export const fallbackDietTodayPayload = {
  daily_target: 2000,
  suggestions: ['晚餐补足优质蛋白', '控制额外油脂', '增加一份深色蔬菜'],
}

const mealTypeAliases = {
  breakfast: ['breakfast', '早餐', '早饭', 'morning'],
  lunch: ['lunch', '午餐', '中餐', 'noon'],
  dinner: ['dinner', '晚餐', '晚饭', 'supper', 'evening'],
}

const mealOrder = ['breakfast', 'lunch', 'dinner']

const clamp = (value, min, max) => {
  return Math.min(max, Math.max(min, value))
}

const toNumber = (value, fallback = 0) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const resolveMealKey = (mealType) => {
  const normalized = String(mealType || '').trim().toLowerCase()

  return mealOrder.find((key) => {
    return mealTypeAliases[key].some((alias) => normalized.includes(alias.toLowerCase()))
  })
}

const buildMealCardFromRecords = (mealKey, records) => {
  const fallbackTemplate = fallbackMealTemplates[mealKey]

  if (!records.length) {
    return fallbackTemplate
  }

  const totalCalories = records.reduce((sum, record) => sum + toNumber(record.calories), 0)
  const latestRecord = records[records.length - 1]
  const countLabel = records.length > 1 ? `${records.length} 项` : '1 项'
  const latestName = latestRecord.name || latestRecord.food_name || latestRecord.dish_name

  return {
    key: mealKey,
    period: fallbackTemplate.period,
    title: latestName || `${fallbackTemplate.period}已记录 ${countLabel}`,
    description: latestRecord.description || latestRecord.note || `已同步真实记录 ${countLabel}，热量按接口结果累计`,
    calories: totalCalories || fallbackTemplate.calories,
    badge: '真实记录',
    ctaLabel: '记录用餐',
    tone: fallbackTemplate.tone,
    isReal: true,
  }
}

const buildMealCards = (records) => {
  const groupedRecords = {
    breakfast: [],
    lunch: [],
    dinner: [],
  }

  records.forEach((record) => {
    const mealKey = resolveMealKey(record.meal_type)
    if (mealKey) {
      groupedRecords[mealKey].push(record)
    }
  })

  return mealOrder.map((mealKey) => buildMealCardFromRecords(mealKey, groupedRecords[mealKey]))
}

const buildIntakeNote = (progressPercent, remainingCalories) => {
  if (remainingCalories <= 0) {
    return '今天的热量目标已经打满，晚餐建议轻一点。'
  }

  if (progressPercent >= 70) {
    return '节奏保持得很好，晚餐补足蛋白和蔬菜就很稳。'
  }

  if (progressPercent >= 40) {
    return '中段节奏不错，晚餐继续把控油脂即可。'
  }

  return '前半天摄入偏轻，晚餐可以安心补一点主食和蛋白。'
}

const buildDinnerDescription = (remainingCalories, suggestions) => {
  const suggestionLine = suggestions[0] || '晚餐优先补足优质蛋白和蔬菜。'

  if (remainingCalories <= 360) {
    return `今晚更适合走轻盈路线，${suggestionLine}`
  }

  if (remainingCalories >= 700) {
    return `剩余空间充足，可以安排一份有主食的暖碗套餐，${suggestionLine}`
  }

  return `把热量留给真正有饱腹感的食材，${suggestionLine}`
}

// Why: keep API compatibility and demo fallback logic in one place so the redesigned diet page consumes a stable view-model only; Scope: diet H5/home data mapping for calorie ring, macro cards, meal list, and AI dinner module; Verify: `uv run --with playwright python tests/e2e/mobile_diet_preview_smoke.py`.
export const buildDietHomeViewModel = (homePayload, todayPayload) => {
  const resolvedHome = homePayload || fallbackDietHomePayload
  const resolvedToday = todayPayload || fallbackDietTodayPayload
  const records = Array.isArray(resolvedHome.records) ? resolvedHome.records : []
  const mealCards = buildMealCards(records)
  const fallbackCalories = mealCards.reduce((sum, meal) => sum + toNumber(meal.calories), 0)
  const hasRealRecords = records.length > 0
  const calorieTarget = toNumber(resolvedHome.calorie_target || resolvedToday.daily_target, fallbackDietHomePayload.calorie_target)
  const calorieConsumed = hasRealRecords
    ? toNumber(resolvedHome.calorie_consumed, fallbackCalories)
    : toNumber(resolvedHome.calorie_consumed, 0) > 0
      ? toNumber(resolvedHome.calorie_consumed, fallbackCalories)
      : fallbackCalories
  const remainingCalories = Math.max(0, calorieTarget - calorieConsumed)
  const progressPercent = calorieTarget ? clamp(Math.round((calorieConsumed / calorieTarget) * 100), 0, 100) : 0
  const suggestionList = Array.isArray(resolvedToday.suggestions) && resolvedToday.suggestions.length
    ? resolvedToday.suggestions
    : fallbackDietTodayPayload.suggestions

  const macro = resolvedHome.macro || fallbackDietHomePayload.macro
  const nutrientCards = [
    {
      key: 'protein',
      label: '蛋白质',
      value: `${toNumber(macro.protein, fallbackDietHomePayload.macro.protein)}g`,
      helper: `目标 ${fallbackMacroGoals.protein}g`,
      progress: clamp(Math.round((toNumber(macro.protein, fallbackDietHomePayload.macro.protein) / fallbackMacroGoals.protein) * 100), 22, 100),
      tone: 'tone-protein',
    },
    {
      key: 'carb',
      label: '碳水',
      value: `${toNumber(macro.carb, fallbackDietHomePayload.macro.carb)}g`,
      helper: `目标 ${fallbackMacroGoals.carb}g`,
      progress: clamp(Math.round((toNumber(macro.carb, fallbackDietHomePayload.macro.carb) / fallbackMacroGoals.carb) * 100), 22, 100),
      tone: 'tone-carb',
    },
    {
      key: 'fat',
      label: '脂肪',
      value: `${toNumber(macro.fat, fallbackDietHomePayload.macro.fat)}g`,
      helper: `目标 ${fallbackMacroGoals.fat}g`,
      progress: clamp(Math.round((toNumber(macro.fat, fallbackDietHomePayload.macro.fat) / fallbackMacroGoals.fat) * 100), 22, 100),
      tone: 'tone-fat',
    },
    {
      key: 'water',
      label: '水分',
      value: '1.2L',
      helper: `目标 ${fallbackMacroGoals.water.toFixed(1)}L`,
      progress: 60,
      tone: 'tone-water',
    },
  ]

  return {
    calorieTarget,
    calorieConsumed,
    remainingCalories,
    progressPercent,
    intakeNote: buildIntakeNote(progressPercent, remainingCalories),
    intakeTag: hasRealRecords ? '已同步真实记录' : '暂无真实记录，先看演示搭配',
    recordSummary: hasRealRecords ? '优先展示真实记录，缺失餐次保留演示结构' : '记录为空时自动展示早餐 / 午餐 / 晚餐示例',
    nutrients: nutrientCards,
    meals: mealCards,
    suggestions: suggestionList,
    aiDinner: {
      title: remainingCalories <= 360 ? '香煎鳕鱼羽衣甘蓝轻碗' : '柠香鸡腿南瓜暖沙拉碗',
      calories: remainingCalories <= 360 ? 328 : 436,
      helper: suggestionList[1] || '结合今日摄入节奏生成',
      description: buildDinnerDescription(remainingCalories, suggestionList),
      chips: suggestionList.slice(0, 3),
    },
  }
}
