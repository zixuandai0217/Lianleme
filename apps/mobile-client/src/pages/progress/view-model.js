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

const buildStatCard = (label, value, unit, badge = '', tone = 'neutral') => {
  return { label, value, unit, badge, tone }
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

// keep real progress payloads and local demo metric modes in one builder; progress home data shaping only; verify with `uv run --with playwright python tests/e2e/mobile_progress_preview_smoke.py`.
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
      headerSubtitle: '继续加油，离目标更近了',
      hero: {
        label: '今日体重',
        value: formatValue(currentWeight),
        unit: 'kg',
        progressText: `目标进度: ${goalProgressPercent}%`,
        progressPercent: goalProgressPercent,
        changeText: `较上周 ${formatSignedValue(weeklyChange, 'kg')}`,
        changeTone: weeklyChange <= 0 ? 'good' : 'warn',
        helper: distanceToGoal > 0 ? `距离目标还差 ${formatValue(distanceToGoal)} kg` : '已经达到阶段目标，继续保持',
        ctaLabel: '+ 记录体重',
      },
      statCards: [
        buildStatCard('连续记录', `${streakDays}`, '天'),
        buildStatCard('平均摄入', `${avgIntake}`, 'kcal'),
        buildStatCard('平均消耗', `${avgBurn}`, 'kcal'),
        buildStatCard('当前 BMI', formatValue(bmiValue), '', bmiStatus, 'good'),
      ],
      chart: {
        title: '体重趋势图',
        unit: 'kg',
        values: weightSeriesByRange[activeRange],
        axisLabels: sampleLabels(rangeLabels),
        summary: buildChartSummary('weight', weightSeriesByRange[activeRange], 'kg', rangeLabel),
      },
      insight: {
        title: '智能建议 (AI)',
        text: resolvedWeekly.ai_suggestion || '继续保持稳定记录，晚餐优先蛋白和蔬菜的组合，会更容易把体重曲线压低。',
      },
    },
    bodyFat: {
      headerSubtitle: '体脂曲线继续向理想区间靠近',
      hero: {
        label: '当前体脂',
        value: formatValue(bodyFatCurrent),
        unit: '%',
        progressText: '减脂进度: 61%',
        progressPercent: 61,
        changeText: `较上周 ${formatSignedValue(-0.6, '%')}`,
        changeTone: 'good',
        helper: '继续保持力量训练和蛋白摄入，体脂会更稳地往下走',
        ctaLabel: '+ 记录体脂',
      },
      statCards: [
        buildStatCard('减脂效率', formatValue(0.6), '%'),
        buildStatCard('平均摄入', `${avgIntake}`, 'kcal'),
        buildStatCard('力量训练', '4', '次'),
        buildStatCard('体脂分区', formatValue(bodyFatCurrent), '', bodyFatCurrent < 25 ? '轻盈' : '稳态', 'good'),
      ],
      chart: {
        title: '体脂趋势图',
        unit: '%',
        values: bodyFatSeriesByRange[activeRange],
        axisLabels: sampleLabels(rangeLabels),
        summary: buildChartSummary('bodyFat', bodyFatSeriesByRange[activeRange], '%', rangeLabel),
      },
      insight: {
        title: '智能建议 (AI)',
        text: `近${rangeLabel}体脂走势比体重更稳，建议把晚餐的优质蛋白固定下来，恢复日也别忽略轻量活动。`,
      },
    },
    measurement: {
      headerSubtitle: '围度正在悄悄收紧，状态很稳',
      hero: {
        label: '当前围度',
        value: formatValue(measurementCurrent),
        unit: 'cm',
        progressText: '围度进度: 58%',
        progressPercent: 58,
        changeText: `较上周 ${formatSignedValue(-1.6, 'cm')}`,
        changeTone: 'good',
        helper: '腰围的变化通常比体重更敏感，继续保持作息会更容易看见反馈',
        ctaLabel: '+ 记录围度',
      },
      statCards: [
        buildStatCard('腰围变化', formatValue(-1.6), 'cm'),
        buildStatCard('腰臀比', '0.82', ''),
        buildStatCard('平均消耗', `${avgBurn}`, 'kcal'),
        buildStatCard('紧致状态', formatValue(measurementCurrent), '', '收紧', 'good'),
      ],
      chart: {
        title: '围度趋势图',
        unit: 'cm',
        values: measurementSeriesByRange[activeRange],
        axisLabels: sampleLabels(rangeLabels),
        summary: buildChartSummary('measurement', measurementSeriesByRange[activeRange], 'cm', rangeLabel),
      },
      insight: {
        title: '智能建议 (AI)',
        text: `围度回落比秤上的数字更能说明状态变化，建议本周继续保持核心训练并把夜宵压到最少。`,
      },
    },
    history: {
      headerSubtitle: '记录越稳定，趋势判断越准确',
      hero: {
        label: '记录完整度',
        value: `${historyCurrent}`,
        unit: '%',
        progressText: '完成度: 86%',
        progressPercent: historyCurrent,
        changeText: `较上周 ${formatSignedValue(8, '%', 0)}`,
        changeTone: 'good',
        helper: `本周已经完成 ${weeklyCheckins}/7 次关键记录，继续保持明早空腹称重会更稳`,
        ctaLabel: '+ 记录历史',
      },
      statCards: [
        buildStatCard('连续记录', `${streakDays}`, '天'),
        buildStatCard('本周打卡', `${weeklyCheckins}`, '次'),
        buildStatCard('最长连续', `${longestStreak}`, '天'),
        buildStatCard('下次提醒', fallbackHistoryState.reminderTime, '', '已开启', 'good'),
      ],
      chart: {
        title: '记录趋势图',
        unit: '%',
        values: historySeriesByRange[activeRange],
        axisLabels: sampleLabels(rangeLabels),
        summary: buildChartSummary('history', historySeriesByRange[activeRange], '%', rangeLabel),
      },
      insight: {
        title: '智能建议 (AI)',
        text: '记录频率越稳定，后续给你的建议就越精准。建议固定晨起和晚饭后两个打点时刻，减少遗漏。',
      },
    },
  }

  const activeState = metricStates[activeMetric] || metricStates.weight

  return {
    headerTitle: '嗨，今天瘦了么？',
    headerSubtitle: activeState.headerSubtitle,
    hero: activeState.hero,
    statCards: activeState.statCards,
    chart: activeState.chart,
    insight: activeState.insight,
    metricTabs: METRIC_TABS.map((item) => ({ ...item, active: item.key === activeMetric })),
    rangeTabs: RANGE_TABS.map((item) => ({ ...item, active: item.key === activeRange })),
    quickActions: [
      { key: 'profile', label: '个人中心', action: 'profile', path: resolvedHome.my_entry?.path || fallbackProgressHomePayload.my_entry.path },
      { key: 'reminder', label: '记录提醒', action: 'toast', toast: '记录提醒即将开放' },
      { key: 'about', label: '关于', action: 'toast', toast: '关于页即将开放' },
    ],
    secondaryActionLabel: activeMetric === 'history' ? '查看周报' : '分享进展',
    footerNote: `昵称 ${pickText(resolvedProfile.nickname, fallbackProfilePayload.nickname)} · 目标 ${formatValue(targetWeight)} kg`,
  }
}

export const fallbackProgressPayloads = {
  home: fallbackProgressHomePayload,
  profile: fallbackProfilePayload,
  trend: fallbackTrendPayload,
  weekly: fallbackWeeklyReportPayload,
}
