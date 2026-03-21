<template>
  <!-- keep the progress home focused on a weekly-report-first story while preserving access to detailed trend filters and profile entry; progress home template only; verify by opening the progress tab in localhost:5173 and checking the report, summary, trend, and coach sections. -->
  <view class="page app-mobile-page app-mobile-page--with-tabbar">
    <view class="phone-shell app-mobile-shell">
      <view class="topbar app-mobile-topbar">
        <view class="brand-chip app-mobile-brand">
          <view class="brand-mark app-mobile-mark">
            <text class="brand-mark-glyph">◎</text>
          </view>
          <view class="brand-copy app-mobile-copy">
            <text class="eyebrow app-mobile-eyebrow">{{ pageModel.headerEyebrow }}</text>
            <text class="headline app-mobile-headline">{{ pageModel.headerTitle }}</text>
            <text class="subhead">{{ pageModel.headerSubtitle }}</text>
          </view>
        </view>

        <view class="share-button app-mobile-float-chip" @click="handleShareAction">
          <text class="share-glyph">↗</text>
        </view>
      </view>

      <view class="report-card">
        <view class="report-head">
          <text class="report-label">{{ pageModel.weeklyHero.label }}</text>
          <text class="report-badge">{{ pageModel.weeklyHero.badge }}</text>
        </view>

        <view class="report-headline-row">
          <text class="report-headline">{{ pageModel.weeklyHero.headline }}</text>
          <text class="report-emoji">{{ pageModel.weeklyHero.emoji }}</text>
        </view>

        <text class="report-helper">{{ pageModel.weeklyHero.helper }}</text>

        <view class="report-footer">
          <text class="report-change" :class="pageModel.weeklyHero.changeTone">{{ pageModel.weeklyHero.changeText }}</text>
          <text class="report-note">{{ pageModel.weeklyHero.footerNote }}</text>
        </view>
      </view>

      <view class="summary-card app-mobile-card">
        <view class="section-heading">
          <view>
            <text class="section-title">{{ pageModel.dietSummary.title }}</text>
            <text class="section-note">{{ pageModel.dietSummary.helper }}</text>
          </view>
        </view>

        <view class="diet-metrics">
          <view
            v-for="card in pageModel.dietSummary.cards"
            :key="card.key"
            class="diet-metric"
            :class="card.tone"
          >
            <text class="diet-metric-label">{{ card.label }}</text>
            <view class="diet-metric-value-row">
              <text class="diet-metric-value">{{ card.value }}</text>
              <text class="diet-metric-unit">{{ card.unit }}</text>
            </view>
          </view>
        </view>

        <view class="macro-row">
          <view
            v-for="macro in pageModel.dietSummary.macros"
            :key="macro.key"
            class="macro-item"
          >
            <view class="macro-ring" :style="getMacroRingStyle(macro.percent, macro.tone)">
              <view class="macro-ring-inner">
                <text class="macro-percent">{{ macro.percent }}%</text>
              </view>
            </view>
            <text class="macro-label">{{ macro.label }}</text>
          </view>
        </view>
      </view>

      <view class="summary-card app-mobile-card">
        <view class="section-heading">
          <view>
            <text class="section-title">{{ pageModel.workoutSummary.title }}</text>
            <text class="section-note">{{ pageModel.workoutSummary.helper }}</text>
          </view>
        </view>

        <view class="workout-stats">
          <view
            v-for="item in pageModel.workoutSummary.stats"
            :key="item.key"
            class="workout-stat"
          >
            <text class="workout-stat-label">{{ item.label }}</text>
            <view class="workout-stat-value-row">
              <text class="workout-stat-value">{{ item.value }}</text>
              <text class="workout-stat-unit">{{ item.unit }}</text>
            </view>
          </view>
        </view>

        <view class="week-strip">
          <view
            v-for="day in pageModel.workoutSummary.days"
            :key="day.label"
            class="week-day"
            :class="{ active: day.active, emphasis: day.emphasis }"
          >
            <text class="week-day-label">{{ day.label }}</text>
            <view class="week-day-dot"></view>
          </view>
        </view>
      </view>

      <view class="trend-card app-mobile-card">
        <view class="trend-top">
          <view>
            <text class="section-title">{{ pageModel.trendSnapshot.title }}</text>
            <text class="section-note">{{ pageModel.trendSnapshot.helper }}</text>
          </view>
          <text class="trend-badge" :class="pageModel.trendSnapshot.badgeTone">{{ pageModel.trendSnapshot.badge }}</text>
        </view>

        <!-- keep the trend plot on-device and driven by the active metric/range state so the weekly report still exposes detailed progress context; progress chart module only; verify by switching metric and range chips in localhost:5173. -->
        <view class="chart-shell">
          <svg class="chart-svg" :viewBox="`0 0 ${chartGeometry.width} ${chartGeometry.height}`" preserveAspectRatio="none">
            <defs>
              <linearGradient id="progressAreaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="rgba(242, 17, 98, 0.26)" />
                <stop offset="100%" stop-color="rgba(242, 17, 98, 0)" />
              </linearGradient>
            </defs>
            <path class="chart-area" :d="chartGeometry.areaPath"></path>
            <path class="chart-line" :d="chartGeometry.linePath"></path>
            <circle
              v-for="marker in chartGeometry.markers"
              :key="marker.key"
              class="chart-marker"
              :cx="marker.x"
              :cy="marker.y"
              r="4.5"
            ></circle>
          </svg>

          <view class="chart-axis">
            <text
              v-for="label in pageModel.chart.axisLabels"
              :key="label"
              class="axis-label"
            >
              {{ label }}
            </text>
          </view>
        </view>
      </view>

      <view class="detail-card app-mobile-card">
        <view class="detail-top">
          <view>
            <text class="section-title">{{ pageModel.detailPanel.title }}</text>
            <text class="section-note">{{ pageModel.detailPanel.helper }}</text>
          </view>

          <view class="mini-link" @click="handleDetailAction">{{ pageModel.detailPanel.ctaLabel }}</view>
        </view>

        <view class="metric-tabs">
          <view
            v-for="item in pageModel.metricTabs"
            :key="item.key"
            class="metric-chip"
            :class="{ active: item.active }"
            @click="setActiveMetric(item.key)"
          >
            {{ item.label }}
          </view>
        </view>

        <view class="range-switch">
          <view
            v-for="item in pageModel.rangeTabs"
            :key="item.key"
            class="range-chip"
            :class="{ active: item.active }"
            @click="setActiveRange(item.key)"
          >
            {{ item.label }}
          </view>
        </view>

        <text class="detail-insight">{{ pageModel.chart.summary }} · {{ pageModel.detailPanel.insight }}</text>
      </view>

      <view class="coach-card">
        <view class="coach-orb coach-orb-large"></view>
        <view class="coach-orb coach-orb-small"></view>
        <text class="coach-title">{{ pageModel.coachRecommendation.title }}</text>
        <text class="coach-text">{{ pageModel.coachRecommendation.text }}</text>

        <view class="coach-tags">
          <text
            v-for="tag in pageModel.coachRecommendation.tags"
            :key="tag"
            class="coach-tag"
          >
            {{ tag }}
          </text>
        </view>
      </view>

      <view class="actions-strip app-mobile-card">
        <view
          v-for="item in pageModel.secondaryActions"
          :key="item.key"
          class="action-item"
          @click="handleQuickAction(item)"
        >
          <view class="action-icon">
            <text class="action-glyph">{{ resolveActionGlyph(item.key) }}</text>
          </view>
          <text class="action-label">{{ item.label }}</text>
        </view>
      </view>

      <view class="status-strip app-mobile-status-strip" v-if="loading || error">
        <text v-if="loading">正在同步本周周报数据...</text>
        <text v-else>{{ error }}</text>
      </view>
    </view>
    <MobileTabBar v-if="!previewShell" current-tab="progress" />
  </view>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'
import MobileTabBar from '../../components/MobileTabBar.vue'
import { requireMobileAuth } from '../../lib/authSession'
import { hideNativeTabBar } from '../../lib/tabbar'
import { buildProgressHomeViewModel, fallbackProgressPayloads } from './view-model'

const previewShell = inject('previewShell', null)
const activeMetric = ref('weight')
const activeRange = ref('7d')
const homeProgress = ref(fallbackProgressPayloads.home)
const profile = ref(fallbackProgressPayloads.profile)
const trend = ref(fallbackProgressPayloads.trend)
const weeklyReport = ref(fallbackProgressPayloads.weekly)
const loading = ref(false)
const error = ref('')

// keep the progress tab on the shared custom bottom nav so the detailed-trend page no longer falls back to the generic system tab bar; progress tab runtime shell only; verify by opening `瘦了么` in mini-program preview and checking the custom white nav remains pinned.
const syncRuntimeTabBar = () => {
  if (!previewShell) {
    hideNativeTabBar()
  }
}

// keep the page component focused on fetch orchestration while the view-model owns all weekly-report shaping and fallback behavior; progress page fetch/render flow only; verify with `uv run --with playwright python tests/e2e/mobile_progress_preview_smoke.py`.
const pageModel = computed(() => {
  return buildProgressHomeViewModel({
    homePayload: homeProgress.value,
    profilePayload: profile.value,
    trendPayload: trend.value,
    weeklyReportPayload: weeklyReport.value,
    activeMetric: activeMetric.value,
    activeRange: activeRange.value,
  })
})

// keep the report chart geometry derived locally from the active view-model so tab/range interactions stay instant in preview and mini-program modes; progress trend geometry only; verify by switching metric and range chips and checking the curve updates immediately.
const chartGeometry = computed(() => {
  const width = 320
  const height = 188
  const left = 8
  const right = 8
  const top = 14
  const bottom = 28
  const values = pageModel.value.chart.values
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const usableWidth = width - left - right
  const usableHeight = height - top - bottom
  const stepX = values.length > 1 ? usableWidth / (values.length - 1) : usableWidth
  const points = values.map((value, index) => {
    return {
      key: `${index}-${value}`,
      x: roundCoordinate(left + stepX * index),
      y: roundCoordinate(top + ((max - value) / range) * usableHeight),
    }
  })
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`).join(' ')
  const areaPath = `${linePath} L ${points[points.length - 1].x},${height - bottom} L ${points[0].x},${height - bottom} Z`
  const markerIndexes = [...new Set([0, Math.round((values.length - 1) * 0.42), values.length - 1])]
  const markers = markerIndexes.map((index) => points[index])

  return {
    width,
    height,
    linePath,
    areaPath,
    markers,
  }
})

const macroToneMap = {
  protein: ['#f21162', '#ff6a8b'],
  carb: ['#ff8c45', '#ffb35b'],
  fat: ['#ff9aa8', '#ffc5cd'],
}

const roundCoordinate = (value) => {
  return Number(value.toFixed(2))
}

const getMacroRingStyle = (percent, tone) => {
  const [startColor, endColor] = macroToneMap[tone] || macroToneMap.protein
  const degrees = Math.round((percent / 100) * 360)

  return {
    background: `conic-gradient(${startColor} 0deg, ${endColor} ${degrees}deg, rgba(236, 240, 247, 0.96) ${degrees}deg 360deg)`,
  }
}

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const handleShareAction = () => {
  showToast('分享周报即将开放')
}

const handleDetailAction = () => {
  showToast('详细趋势即将开放')
}

const resolveActionGlyph = (key) => {
  const glyphMap = {
    profile: '我',
    reminder: '铃',
    history: '史',
  }

  return glyphMap[key] || '•'
}

const openProfile = (path) => {
  if (previewShell?.openPreviewPage) {
    previewShell.openPreviewPage('profile')
    return
  }

  if (typeof uni !== 'undefined' && typeof uni.navigateTo === 'function') {
    uni.navigateTo({
      url: path,
      fail: () => showToast('个人中心预览页暂不可用'),
    })
    return
  }

  showToast('个人中心预览页暂不可用')
}

const handleQuickAction = (item) => {
  if (item.action === 'profile') {
    openProfile(item.path)
    return
  }

  showToast(item.toast)
}

const setActiveMetric = (metricKey) => {
  activeMetric.value = metricKey
}

const setActiveRange = (rangeKey) => {
  activeRange.value = rangeKey
}

const isProgressHomePayloadValid = (payload) => {
  return payload && (Number.isFinite(Number(payload.weight)) || Number.isFinite(Number(payload.target_weight)))
}

const isProfilePayloadValid = (payload) => {
  return payload && Number.isFinite(Number(payload.height_cm))
}

const isTrendPayloadValid = (payload) => {
  return payload && Array.isArray(payload.weights) && payload.weights.length > 0
}

const isWeeklyReportPayloadValid = (payload) => {
  return payload && (Number.isFinite(Number(payload.weight_change_kg)) || Number.isFinite(Number(payload.calories_in)))
}

const fetchProgressDashboard = async () => {
  loading.value = true
  error.value = ''

  const messages = []
  const [homeResult, profileResult, trendResult, weeklyResult] = await Promise.allSettled([
    apiGet('/home/progress'),
    apiGet('/profile'),
    apiGet('/profile/trend'),
    apiGet('/report/weekly'),
  ])

  if (homeResult.status === 'fulfilled' && isProgressHomePayloadValid(homeResult.value)) {
    homeProgress.value = { ...fallbackProgressPayloads.home, ...homeResult.value }
  } else {
    messages.push('首页聚合已切换到本地演示')
  }

  if (profileResult.status === 'fulfilled' && isProfilePayloadValid(profileResult.value)) {
    profile.value = { ...fallbackProgressPayloads.profile, ...profileResult.value }
  } else {
    messages.push('资料接口已切换到本地演示')
  }

  if (trendResult.status === 'fulfilled' && isTrendPayloadValid(trendResult.value)) {
    trend.value = { ...fallbackProgressPayloads.trend, ...trendResult.value }
  } else {
    messages.push('趋势接口已切换到本地演示')
  }

  if (weeklyResult.status === 'fulfilled' && isWeeklyReportPayloadValid(weeklyResult.value)) {
    weeklyReport.value = { ...fallbackProgressPayloads.weekly, ...weeklyResult.value }
  } else {
    messages.push('周报接口已切换到本地演示')
  }

  if (homeResult.status === 'rejected') {
    messages.push(`progress 首页请求失败：${homeResult.reason?.message || homeResult.reason?.errMsg || 'unknown'}`)
  }

  if (profileResult.status === 'rejected') {
    messages.push(`profile 请求失败：${profileResult.reason?.message || profileResult.reason?.errMsg || 'unknown'}`)
  }

  if (trendResult.status === 'rejected') {
    messages.push(`trend 请求失败：${trendResult.reason?.message || trendResult.reason?.errMsg || 'unknown'}`)
  }

  if (weeklyResult.status === 'rejected') {
    messages.push(`weekly 请求失败：${weeklyResult.reason?.message || weeklyResult.reason?.errMsg || 'unknown'}`)
  }

  error.value = messages.join(' · ')
  loading.value = false
}

// gate the progress home behind mobile session state before any data fetch starts; progress entry guard only; verify by opening the page without login in mini-program preview.
onMounted(() => {
  const session = requireMobileAuth()
  if (!session) {
    return
  }

  syncRuntimeTabBar()
  void fetchProgressDashboard()
})
</script>

<style scoped lang="scss">
/* Why: rebuild the progress tab into a weekly-report-first dashboard that mirrors the provided reference while still exposing deeper trend filters; Scope: progress page presentation only in H5 and mini-program previews; Verify: localhost:5173 progress tab shows the weekly report, diet/workout summaries, trend chart, detail chips, and AI coach card. */
.page,
.page *,
.page *::before,
.page *::after {
  box-sizing: border-box;
}

.page {
  background:
    radial-gradient(circle at top left, rgba(242, 17, 98, 0.18), transparent 30%),
    radial-gradient(circle at top right, rgba(255, 181, 91, 0.22), transparent 28%),
    radial-gradient(circle at bottom right, rgba(144, 172, 255, 0.14), transparent 22%),
    linear-gradient(180deg, #1c212f 0%, #282f43 18%, #f8f0f7 18%, #f2f5fb 100%);
}

.phone-shell {
  padding: 18px 16px 20px;
}

.topbar {
  gap: 12px;
}

.brand-mark {
  color: var(--mobile-brand-primary);
}

.brand-mark-glyph {
  font-size: 20px;
  font-weight: 700;
}

.subhead {
  font-size: 13px;
  color: #8a92aa;
  font-weight: 700;
}

.share-button {
  color: var(--mobile-brand-primary);
}

.share-glyph {
  font-size: 18px;
  font-weight: 800;
  line-height: 1;
}

.report-card,
.coach-card {
  position: relative;
  overflow: hidden;
  margin-top: 18px;
  border-radius: 30px;
}

.report-card {
  padding: 20px 18px;
  background:
    radial-gradient(circle at top right, rgba(255, 223, 187, 0.28), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 248, 252, 0.98));
  box-shadow:
    0 24px 44px rgba(28, 34, 51, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.report-head,
.report-headline-row,
.section-heading,
.trend-top,
.detail-top,
.diet-metrics,
.workout-stats,
.week-strip,
.macro-row,
.metric-tabs,
.range-switch,
.coach-tags,
.actions-strip {
  display: flex;
}

.report-head,
.trend-top,
.detail-top {
  align-items: center;
  justify-content: space-between;
}

.report-label,
.section-title {
  color: var(--mobile-ink);
  font-weight: 800;
}

.report-label {
  font-size: 14px;
}

.report-badge,
.trend-badge,
.mini-link {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}

.report-badge {
  background: rgba(242, 17, 98, 0.08);
  color: var(--mobile-brand-primary);
}

.report-headline-row {
  align-items: flex-start;
  gap: 10px;
  margin-top: 14px;
}

.report-headline {
  flex: 1;
  font-size: 27px;
  line-height: 1.18;
  font-weight: 900;
  color: var(--mobile-ink);
}

.report-emoji {
  font-size: 28px;
  line-height: 1;
}

.report-helper,
.section-note,
.detail-insight,
.coach-text,
.report-note {
  color: #8a92aa;
}

.report-helper {
  display: block;
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.6;
}

.report-footer {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 16px;
}

.report-change {
  font-size: 13px;
  font-weight: 800;
}

.report-change.good,
.trend-badge.good {
  color: #1fb878;
}

.report-change.warn,
.trend-badge.warn {
  color: #ff855a;
}

.report-note {
  font-size: 12px;
}

.summary-card,
.trend-card,
.detail-card,
.actions-strip {
  margin-top: 18px;
}

.summary-card,
.trend-card,
.detail-card {
  padding: 18px 16px;
}

.section-heading {
  align-items: flex-start;
  justify-content: space-between;
}

.section-title {
  display: block;
  font-size: 18px;
}

.section-note {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.diet-metrics,
.workout-stats {
  gap: 12px;
  margin-top: 18px;
}

.diet-metric,
.workout-stat {
  flex: 1;
  min-width: 0;
  padding: 14px;
  border-radius: 22px;
}

.diet-metric.primary {
  background: linear-gradient(180deg, rgba(242, 17, 98, 0.08), rgba(255, 228, 236, 0.56));
  border: 1px solid rgba(242, 17, 98, 0.12);
}

.diet-metric.neutral {
  background: linear-gradient(180deg, rgba(244, 247, 252, 0.9), rgba(236, 241, 248, 0.9));
  border: 1px solid rgba(208, 216, 230, 0.56);
}

.diet-metric-label,
.workout-stat-label,
.macro-label,
.week-day-label,
.axis-label,
.action-label {
  color: #9098af;
}

.diet-metric-label,
.workout-stat-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
}

.diet-metric-value-row,
.workout-stat-value-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin-top: 10px;
}

.diet-metric-value,
.workout-stat-value {
  font-size: 19px;
  line-height: 1;
  font-weight: 900;
  color: var(--mobile-ink);
}

.diet-metric.primary .diet-metric-value {
  color: var(--mobile-brand-primary);
}

.diet-metric-unit,
.workout-stat-unit {
  font-size: 12px;
  color: #69728a;
}

.macro-row {
  justify-content: space-between;
  gap: 10px;
  margin-top: 18px;
}

.macro-item {
  flex: 1;
  min-width: 0;
  text-align: center;
}

.macro-ring {
  width: 64px;
  height: 64px;
  margin: 0 auto;
  padding: 5px;
  border-radius: 50%;
}

.macro-ring-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.macro-percent {
  font-size: 12px;
  font-weight: 800;
  color: var(--mobile-ink);
}

.macro-label {
  display: block;
  margin-top: 10px;
  font-size: 12px;
  font-weight: 700;
}

.week-strip {
  justify-content: space-between;
  gap: 8px;
  margin-top: 18px;
}

.week-day {
  flex: 1;
  min-width: 0;
  text-align: center;
}

.week-day-label {
  display: block;
  font-size: 11px;
}

.week-day-dot {
  width: 8px;
  height: 8px;
  margin: 10px auto 0;
  border-radius: 50%;
  background: #d9dfeb;
}

.week-day.active .week-day-dot {
  background: var(--mobile-brand-primary);
}

.week-day.emphasis .week-day-dot {
  box-shadow: 0 0 0 4px rgba(242, 17, 98, 0.12);
}

.trend-badge {
  background: rgba(242, 17, 98, 0.08);
}

.chart-shell {
  margin-top: 18px;
}

.chart-svg {
  display: block;
  width: 100%;
  height: 206px;
}

.chart-area {
  fill: url(#progressAreaGradient);
}

.chart-line {
  fill: none;
  stroke: var(--mobile-brand-primary);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.chart-marker {
  fill: var(--mobile-brand-primary);
}

.chart-axis {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  margin-top: 4px;
}

.axis-label {
  text-align: center;
  font-size: 11px;
}

.mini-link {
  flex-shrink: 0;
  background: rgba(242, 17, 98, 0.08);
  color: var(--mobile-brand-primary);
}

.metric-tabs,
.range-switch {
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}

.metric-chip,
.range-chip {
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  color: #7d859c;
  background: #f4f6fb;
}

.metric-chip.active,
.range-chip.active {
  color: var(--mobile-brand-primary);
  background: rgba(242, 17, 98, 0.1);
  box-shadow: inset 0 0 0 1px rgba(242, 17, 98, 0.08);
}

.detail-insight {
  display: block;
  margin-top: 16px;
  font-size: 12px;
  line-height: 1.6;
}

.coach-card {
  padding: 20px 18px;
  background:
    radial-gradient(circle at top right, rgba(255, 180, 91, 0.16), transparent 30%),
    linear-gradient(145deg, #f21162 0%, #f43f71 50%, #ff7a45 100%);
  box-shadow: 0 28px 52px rgba(242, 17, 98, 0.24);
}

.coach-orb {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
}

.coach-orb-large {
  right: -18px;
  top: -10px;
  width: 92px;
  height: 92px;
}

.coach-orb-small {
  right: 18px;
  top: 18px;
  width: 12px;
  height: 12px;
  box-shadow: 26px 12px 0 rgba(255, 255, 255, 0.12), 42px 32px 0 rgba(255, 255, 255, 0.12);
}

.coach-title,
.coach-text,
.coach-tag {
  position: relative;
  z-index: 1;
}

.coach-title {
  display: block;
  font-size: 22px;
  font-weight: 900;
  color: #ffffff;
}

.coach-text {
  display: block;
  margin-top: 14px;
  font-size: 13px;
  line-height: 1.75;
  color: rgba(255, 255, 255, 0.88);
}

.coach-tags {
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 18px;
}

.coach-tag {
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  color: #ffffff;
  font-size: 11px;
  font-weight: 800;
}

.actions-strip {
  justify-content: space-between;
  gap: 10px;
  padding: 14px 12px;
}

.action-item {
  flex: 1;
  min-width: 0;
  text-align: center;
}

.action-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin: 0 auto;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(242, 17, 98, 0.1), rgba(255, 180, 91, 0.1));
}

.action-glyph {
  font-size: 16px;
  font-weight: 900;
  color: var(--mobile-brand-primary);
}

.action-label {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  font-weight: 700;
}

.status-strip {
  background: rgba(255, 255, 255, 0.74);
}

@media (max-width: 375px) {
  .report-head,
  .trend-top,
  .detail-top,
  .diet-metrics,
  .workout-stats {
    flex-direction: column;
    align-items: stretch;
  }

  .macro-row,
  .week-strip,
  .actions-strip {
    gap: 8px;
  }

  .metric-tabs,
  .range-switch {
    gap: 6px;
  }
}
</style>
