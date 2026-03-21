const METRIC_TABS = [
  { key: 'weight', label: '体重' },
  { key: 'bodyFat', label: '体脂' },
  { key: 'measurement', label: '围度' },
  { key: 'history', label: '历史' },
]

const RANGE_TABS = [
  { key: '7d', label: '7天', count: 7 },
  { key: '14d', label: '14天', count: 14 },
  { key: '30d', label: '30天', count: 30 },
]

const fallbackProgressHomePayload = {
  weight: 70,
  target_weight: 65,
  weekly_report_summary: {
    calories_in: 12450,
    calories_out: 3850,
    weight_change_kg: -0.8,
    ai_suggestion: '本周你完成度不错，建议继续保持训练频次并继续稳定饮食。',
  },
  my_entry: {
    sections: ['profile', 'settings', 'export', 'account'],
    path: '/pages/profile/index',
  },
}

const fallbackProfilePayload = {
  nickname: '练了么用户',
  height_cm: 170,
  weight_kg: 70,
  target_weight_kg: 65,
}

const fallbackTrendPayload = {
  days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
  weights: [72.5, 72.2, 71.8, 71.5, 71.3, 71.2, 71.1],
}

const fallbackWeeklyReportPayload = {
  calories_in: 12450,
  calories_out: 3850,
  weight_change_kg: -0.8,
  ai_suggestion: '检测到你本周执行节奏稳定，继续保持晨间称重和晚餐控油会更容易看到体重下降。',
}

const fallbackHistoryState = {
  streakDays: 15,
  weeklyCheckins: 6,
  longestStreak: 21,
  reminderTime: '07:30',
  goalProgressPercent: 65,
}

const WEEKDAY_MAP = {
  Mon: '周一',
  Tue: '周二',
  Wed: '周三',
  Thu: '周四',
  Fri: '周五',
  Sat: '周六',
  Sun: '周日',
}

const WORKOUT_DAY_PRIORITY = [0, 1, 3, 4, 5, 2, 6]

const toNumber = (value, fallback = 0) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const clamp = (value, min, max) => {
  return Math.min(max, Math.max(min, value))
}

const roundTo = (value, digits = 1) => {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

const formatValue = (value, digits = 1) => {
  const normalized = roundTo(value, digits).toFixed(digits)
  return normalized.replace(/\.0$/, '')
}

const formatInteger = (value) => {
  return Math.round(toNumber(value)).toLocaleString('en-US')
}

const formatSignedValue = (value, unit, digits = 1) => {
  const normalized = value > 0 ? `+${formatValue(value, digits)}` : formatValue(value, digits)
  return `${normalized}${unit}`
}

const pickMeaningfulNumber = (...values) => {
  return values.find((value) => Number.isFinite(Number(value)) && Number(value) > 0) ?? values.find((value) => Number.isFinite(Number(value))) ?? 0
}

const pickText = (...values) => {
  return values.find((value) => typeof value === 'string' && value.trim()) || ''
}

const buildDefaultWeekdayLabels = () => {
  const today = new Date()

  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (6 - index))
    return WEEKDAY_MAP[date.toLocaleDateString('en-US', { weekday: 'short' })] || '今日'
  })
}

const buildDateLabels = (count) => {
  const today = new Date()

  return Array.from({ length: count }, (_, index) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (count - 1 - index))
    return `${date.getMonth() + 1}/${date.getDate()}`
  })
}

const sampleLabels = (labels, sampleCount = 7) => {
  if (labels.length <= sampleCount) {
    return labels
  }

  const step = (labels.length - 1) / (sampleCount - 1)
  return Array.from({ length: sampleCount }, (_, index) => {
    return labels[Math.min(labels.length - 1, Math.round(index * step))]
  })
}

const buildExtendedSeries = (baseSeries, totalCount, increment) => {
  const series = [...baseSeries]

  while (series.length < totalCount) {
    const distance = totalCount - series.length
    const variance = ((distance % 3) - 1) * 0.04
    series.unshift(roundTo(series[0] + increment + variance))
  }

  return series
}

const buildHistorySeries = (count, currentValue) => {
  const series = [currentValue]

  while (series.length < count) {
    const distance = count - series.length
    const variance = ((distance % 4) - 1.5) * 1.2
    series.unshift(roundTo(clamp(series[0] - 1.8 + variance, 58, 96)))
  }

  return series
}

const buildWeightSeriesByRange = (trendPayload, currentWeight) => {
  const rawWeights = Array.isArray(trendPayload?.weights) && trendPayload.weights.length
    ? trendPayload.weights.map((weight) => toNumber(weight, currentWeight))
    : fallbackTrendPayload.weights
  const baseSeries = rawWeights.slice(-7)
  const alignedOffset = currentWeight - baseSeries[baseSeries.length - 1]
  const alignedSeries = baseSeries.map((weight) => roundTo(weight + alignedOffset))

  return {
    '7d': alignedSeries,
    '14d': buildExtendedSeries(alignedSeries, 14, 0.14),
    '30d': buildExtendedSeries(alignedSeries, 30, 0.11),
  }
}

const buildRangeLabels = (trendPayload, rangeKey) => {
  const rangeCount = RANGE_TABS.find((item) => item.key === rangeKey)?.count || 7

  if (rangeKey === '7d') {
    const payloadDays = Array.isArray(trendPayload?.days) && trendPayload.days.length === 7
      ? trendPayload.days.map((day) => WEEKDAY_MAP[day] || day)
      : buildDefaultWeekdayLabels()
    return payloadDays
  }

  return buildDateLabels(rangeCount)
}

const resolveCurrentWeight = (profilePayload, homePayload) => {
  return pickMeaningfulNumber(profilePayload?.weight_kg, homePayload?.weight, fallbackProfilePayload.weight_kg)
}

const resolveTargetWeight = (profilePayload, homePayload) => {
  return pickMeaningfulNumber(profilePayload?.target_weight_kg, homePayload?.target_weight, fallbackProfilePayload.target_weight_kg)
}

const resolveHeight = (profilePayload) => {
  return pickMeaningfulNumber(profilePayload?.height_cm, fallbackProfilePayload.height_cm)
}

const resolveWeeklyReport = (weeklyReportPayload, homePayload) => {
  const homeReport = homePayload?.weekly_report_summary || {}

  return {
    calories_in: pickMeaningfulNumber(weeklyReportPayload?.calories_in, homeReport.calories_in, fallbackWeeklyReportPayload.calories_in),
    calories_out: pickMeaningfulNumber(weeklyReportPayload?.calories_out, homeReport.calories_out, fallbackWeeklyReportPayload.calories_out),
    weight_change_kg: Number.isFinite(Number(weeklyReportPayload?.weight_change_kg))
      ? Number(weeklyReportPayload.weight_change_kg)
      : Number.isFinite(Number(homeReport.weight_change_kg))
        ? Number(homeReport.weight_change_kg)
        : fallbackWeeklyReportPayload.weight_change_kg,
    ai_suggestion: pickText(weeklyReportPayload?.ai_suggestion, homeReport.ai_suggestion, fallbackWeeklyReportPayload.ai_suggestion),
  }
}

const buildChartSummary = (modeKey, values, unit, rangeLabel) => {
  const diff = roundTo(values[values.length - 1] - values[0])

  if (modeKey === 'history') {
    const verb = diff >= 0 ? '提升' : '回落'
    return `近${rangeLabel}${verb} ${formatValue(Math.abs(diff), 0)}${unit}`
  }

  const verb = diff <= 0 ? '下降' : '回升'
  return `近${rangeLabel}${verb} ${formatValue(Math.abs(diff))}${unit}`
}

const buildMacroBreakdown = (goalProgressPercent, weeklyChange) => {
  const protein = clamp(Math.round(54 + goalProgressPercent * 0.18), 48, 82)
  const carb = clamp(Math.round(42 + Math.max(-weeklyChange, 0) * 4), 32, 68)
  const fat = clamp(Math.round(24 + Math.max(weeklyChange, -1.2) * 2), 18, 42)

  return [
    { key: 'protein', label: '蛋白质', percent: protein, tone: 'protein' },
    { key: 'carb', label: '碳水', percent: carb, tone: 'carb' },
    { key: 'fat', label: '脂肪', percent: fat, tone: 'fat' },
  ]
}

const buildWorkoutWeek = (activeCount) => {
  const activeIndexes = new Set(WORKOUT_DAY_PRIORITY.slice(0, activeCount))
  const lastActive = WORKOUT_DAY_PRIORITY[Math.max(activeCount - 1, 0)]

  return buildDefaultWeekdayLabels().map((label, index) => {
    return {
      label,
      active: activeIndexes.has(index),
      emphasis: activeIndexes.has(index) && index === lastActive,
    }
  })
}

const buildCoachTags = (weeklyChange, avgIntake, workoutDays) => {
  const tags = weeklyChange <= 0 ? ['# 晨间称重', '# 高蛋白'] : ['# 稳住节奏', '# 控油晚餐']

  if (avgIntake <= 1800) {
    tags.push('# 热量平衡')
  }

  if (workoutDays >= 5) {
    tags.push('# 力量训练')
  }

  return tags.slice(0, 3)
}

const buildWeeklyHeadline = (weeklyChange) => {
  if (weeklyChange < 0) {
    return `嗨，本周你瘦了 ${formatValue(Math.abs(weeklyChange))}kg！`
  }

  if (weeklyChange === 0) {
    return '嗨，本周你稳住了！'
  }

  return `嗨，这周波动了 ${formatValue(weeklyChange)}kg`
}

// keep the progress page driven by existing gateway payloads while reshaping them into a weekly-report-first experience; progress home data shaping only; verify with `uv run --with playwright python tests/e2e/mobile_progress_preview_smoke.py`.
export const buildProgressHomeViewModel = ({
  homePayload,
  profilePayload,
  trendPayload,
  weeklyReportPayload,
  activeMetric = 'weight',
  activeRange = '7d',
} = {}) => {
  const resolvedHome = homePayload || fallbackProgressHomePayload
  const resolvedProfile = profilePayload || fallbackProfilePayload
  const resolvedTrend = trendPayload || fallbackTrendPayload
  const resolvedWeekly = resolveWeeklyReport(weeklyReportPayload, resolvedHome)

  const currentWeight = roundTo(resolveCurrentWeight(resolvedProfile, resolvedHome))
  const targetWeight = roundTo(resolveTargetWeight(resolvedProfile, resolvedHome))
  const heightCm = resolveHeight(resolvedProfile)
  const bmiValue = roundTo(currentWeight / ((heightCm / 100) ** 2))
  const bmiStatus = bmiValue < 18.5 ? '偏低' : bmiValue < 24 ? '正常' : bmiValue < 28 ? '偏高' : '预警'
  const streakDays = fallbackHistoryState.streakDays
  const weeklyCheckins = fallbackHistoryState.weeklyCheckins
  const longestStreak = fallbackHistoryState.longestStreak
  const avgIntake = Math.round((resolvedWeekly.calories_in / 7) / 10) * 10
  const avgBurn = Math.round((resolvedWeekly.calories_out / 7) / 10) * 10
  const weeklyChange = roundTo(resolvedWeekly.weight_change_kg)
  const goalProgressPercent = currentWeight <= targetWeight ? 100 : fallbackHistoryState.goalProgressPercent
  const distanceToGoal = roundTo(Math.max(0, currentWeight - targetWeight))
  const calorieTarget = Math.max(Math.round((resolvedWeekly.calories_in * 1.12) / 50) * 50, resolvedWeekly.calories_in + 400)
  const workoutMinutes = Math.max(120, Math.round((resolvedWeekly.calories_out / 9.2) / 10) * 10)
  const workoutDays = clamp(Math.round(workoutMinutes / 84), 3, 6)
  const weeklyPercentChange = roundTo((weeklyChange / currentWeight) * 100, 1)

  const weightSeriesByRange = buildWeightSeriesByRange(resolvedTrend, currentWeight)
  const bodyFatCurrent = roundTo(clamp(24.6 + Math.max(currentWeight - 70, 0) * 0.25, 18.8, 29.5))
  const measurementCurrent = roundTo(79.8 + Math.max(currentWeight - targetWeight, 0) * 0.5)
  const historyCurrent = 86

  const bodyFatSeriesByRange = Object.fromEntries(
    Object.entries(weightSeriesByRange).map(([rangeKey, values]) => {
      return [rangeKey, values.map((value) => roundTo(bodyFatCurrent + (value - currentWeight) * 0.72))]
    }),
  )

  const measurementSeriesByRange = Object.fromEntries(
    Object.entries(weightSeriesByRange).map(([rangeKey, values]) => {
      return [rangeKey, values.map((value) => roundTo(measurementCurrent + (value - currentWeight) * 1.05))]
    }),
  )

  const historySeriesByRange = Object.fromEntries(
    RANGE_TABS.map((rangeItem) => {
      return [rangeItem.key, buildHistorySeries(rangeItem.count, historyCurrent)]
    }),
  )

  const rangeLabel = RANGE_TABS.find((item) => item.key === activeRange)?.label || '7天'
  const rangeLabels = buildRangeLabels(resolvedTrend, activeRange)

  const metricStates = {
    weight: {
      title: '体重趋势',
      summary: `当前 ${formatValue(currentWeight)} kg · 目标 ${formatValue(targetWeight)} kg`,
      helper: distanceToGoal > 0 ? `距离目标还差 ${formatValue(distanceToGoal)} kg` : '已经达到阶段目标，继续稳定记录',
      values: weightSeriesByRange[activeRange],
      insight: '体重是周报主线，建议固定晨起称重时段。',
    },
    bodyFat: {
      title: '体脂趋势',
      summary: `当前体脂 ${formatValue(bodyFatCurrent)}%`,
      helper: '体脂变化会比体重更平稳，继续保留力量训练。',
      values: bodyFatSeriesByRange[activeRange],
      insight: '体脂走势稳步回落，恢复日也别忽略轻量活动。',
    },
    measurement: {
      title: '围度趋势',
      summary: `当前围度 ${formatValue(measurementCurrent)} cm`,
      helper: '围度回落往往比秤上的数字更早给你反馈。',
      values: measurementSeriesByRange[activeRange],
      insight: '围度正在收紧，建议继续保持核心训练与规律作息。',
    },
    history: {
      title: '记录趋势',
      summary: `本周打卡 ${weeklyCheckins}/7 次`,
      helper: `最长连续 ${longestStreak} 天 · 下次提醒 ${fallbackHistoryState.reminderTime}`,
      values: historySeriesByRange[activeRange],
      insight: '记录越稳定，后续给你的建议就越精准。',
    },
  }

  const activeState = metricStates[activeMetric] || metricStates.weight
  const macroBreakdown = buildMacroBreakdown(goalProgressPercent, weeklyChange)

  return {
    headerEyebrow: 'WEEKLY REPORT',
    headerTitle: '数据周报',
    headerSubtitle: weeklyChange <= 0 ? '这一周的减脂节奏很稳，继续保持。' : '这周先稳住节奏，下一周再把曲线拉回来。',
    weeklyHero: {
      label: '本周数据周报',
      badge: `目标完成 ${goalProgressPercent}%`,
      headline: buildWeeklyHeadline(weeklyChange),
      emoji: weeklyChange <= 0 ? '🥳' : '💪',
      helper: distanceToGoal > 0 ? `继续保持，离你的目标还差 ${formatValue(distanceToGoal)} kg。` : '已经达到阶段目标，继续稳定记录会更容易守住结果。',
      changeText: `较上周 ${formatSignedValue(weeklyChange, 'kg')}`,
      changeTone: weeklyChange <= 0 ? 'good' : 'warn',
      footerNote: `连续记录 ${streakDays} 天 · BMI ${formatValue(bmiValue)} ${bmiStatus}`,
    },
    dietSummary: {
      title: '饮食总结',
      helper: `日均摄入 ${avgIntake} kcal`,
      cards: [
        { key: 'intake', label: '摄入热量', value: formatInteger(resolvedWeekly.calories_in), unit: 'kcal', tone: 'primary' },
        { key: 'target', label: '目标热量', value: formatInteger(calorieTarget), unit: 'kcal', tone: 'neutral' },
      ],
      macros: macroBreakdown,
    },
    workoutSummary: {
      title: '运动总结',
      helper: `本周完成 ${workoutDays}/7 天关键活动`,
      stats: [
        { key: 'duration', label: '累计时长', value: `${workoutMinutes}`, unit: 'min' },
        { key: 'burn', label: '消耗热量', value: formatInteger(resolvedWeekly.calories_out), unit: 'kcal' },
      ],
      days: buildWorkoutWeek(workoutDays),
    },
    trendSnapshot: {
      title: '体重趋势',
      badge: `${weeklyPercentChange > 0 ? '+' : ''}${formatValue(weeklyPercentChange)}%`,
      badgeTone: weeklyPercentChange <= 0 ? 'good' : 'warn',
      helper: `7 天曲线持续 ${weeklyChange <= 0 ? '回落' : '波动'}，${distanceToGoal > 0 ? `距离目标还有 ${formatValue(distanceToGoal)} kg` : '已经进入维稳阶段'}`,
    },
    chart: {
      title: activeState.title,
      unit: activeMetric === 'history' ? '%' : activeMetric === 'bodyFat' ? '%' : activeMetric === 'measurement' ? 'cm' : 'kg',
      values: activeState.values,
      axisLabels: sampleLabels(rangeLabels),
      summary: buildChartSummary(activeMetric, activeState.values, activeMetric === 'history' ? '%' : activeMetric === 'bodyFat' ? '%' : activeMetric === 'measurement' ? 'cm' : 'kg', rangeLabel),
      helper: activeState.helper,
    },
    detailPanel: {
      title: '详细趋势',
      helper: activeState.summary,
      insight: activeState.insight,
      ctaLabel: '查看详细趋势',
    },
    coachRecommendation: {
      title: 'AI 教练建议',
      text: pickText(
        resolvedWeekly.ai_suggestion,
        '继续保持稳定记录，晚餐优先蛋白和蔬菜的组合，会更容易把体重曲线压低。',
      ),
      tags: buildCoachTags(weeklyChange, avgIntake, workoutDays),
    },
    metricTabs: METRIC_TABS.map((item) => ({ ...item, active: item.key === activeMetric })),
    rangeTabs: RANGE_TABS.map((item) => ({ ...item, active: item.key === activeRange })),
    secondaryActions: [
      { key: 'profile', label: '个人中心', action: 'profile', path: resolvedHome.my_entry?.path || fallbackProgressHomePayload.my_entry.path },
      { key: 'reminder', label: '记录提醒', action: 'toast', toast: '记录提醒即将开放' },
      { key: 'history', label: '查看历史', action: 'toast', toast: '历史趋势页即将开放' },
    ],
  }
}

export const fallbackProgressPayloads = {
  home: fallbackProgressHomePayload,
  profile: fallbackProfilePayload,
  trend: fallbackTrendPayload,
  weekly: fallbackWeeklyReportPayload,
}
