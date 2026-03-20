<template>
  <view class="page">
    <view class="phone-shell">
      <view class="topbar">
        <view class="brand-chip">
          <view class="brand-mark">
            <view class="brand-scale"></view>
          </view>
          <view class="brand-copy">
            <text class="headline">{{ pageModel.headerTitle }}</text>
            <text class="subhead">{{ pageModel.headerSubtitle }}</text>
          </view>
        </view>

        <view class="notify-button" @click="showToast('提醒设置即将开放')">
          <view class="notify-icon"></view>
        </view>
      </view>

      <view class="hero-card">
        <view class="hero-header">
          <text class="hero-label">{{ pageModel.hero.label }}</text>
          <text class="hero-progress-chip">{{ pageModel.hero.progressText }}</text>
        </view>

        <view class="hero-value-row">
          <text class="hero-value">{{ pageModel.hero.value }}</text>
          <text class="hero-unit">{{ pageModel.hero.unit }}</text>
        </view>

        <text class="hero-change" :class="pageModel.hero.changeTone">{{ pageModel.hero.changeText }}</text>
        <text class="hero-helper">{{ pageModel.hero.helper }}</text>

        <view class="hero-track">
          <view class="hero-fill" :style="{ width: `${pageModel.hero.progressPercent}%` }"></view>
        </view>

        <view class="hero-actions">
          <view class="hero-primary" @click="handlePrimaryAction">{{ pageModel.hero.ctaLabel }}</view>
          <view class="hero-secondary" @click="handleSecondaryAction">
            <view class="hero-secondary-icon"></view>
          </view>
        </view>
      </view>

      <view class="stats-grid">
        <view
          v-for="card in pageModel.statCards"
          :key="card.label"
          class="stat-card"
        >
          <text class="stat-label">{{ card.label }}</text>
          <view class="stat-value-row">
            <text class="stat-value">{{ card.value }}</text>
            <text v-if="card.unit" class="stat-unit">{{ card.unit }}</text>
            <text v-if="card.badge" class="stat-badge" :class="card.tone">{{ card.badge }}</text>
          </view>
        </view>
      </view>

      <view class="chart-card">
        <view class="chart-header">
          <view>
            <text class="section-title">{{ pageModel.chart.title }}</text>
            <text class="section-note">{{ pageModel.chart.summary }}</text>
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
        </view>

        <!-- keep the progress chart fully driven by local range and metric state so H5 preview can demonstrate all tabs without backend expansion; progress chart module only; verify by switching 7/14/30 and metric tabs in localhost:5173 -->
        <view class="chart-shell">
          <svg class="chart-svg" :viewBox="`0 0 ${chartGeometry.width} ${chartGeometry.height}`" preserveAspectRatio="none">
            <defs>
              <linearGradient id="progressAreaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="rgba(255, 140, 106, 0.34)" />
                <stop offset="100%" stop-color="rgba(255, 140, 106, 0)" />
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

      <view class="mode-strip">
        <view
          v-for="item in pageModel.metricTabs"
          :key="item.key"
          class="mode-item"
          :class="{ active: item.active }"
          @click="setActiveMetric(item.key)"
        >
          <view class="mode-icon" :class="`mode-icon-${item.key}`"></view>
          <text class="mode-label">{{ item.label }}</text>
        </view>
      </view>

      <view class="insight-card">
        <text class="insight-title">{{ pageModel.insight.title }}</text>
        <text class="insight-text">{{ pageModel.insight.text }}</text>
        <view class="insight-button" @click="showToast('详细分析即将开放')">查看详细分析</view>
      </view>

      <view class="quick-actions">
        <view
          v-for="item in pageModel.quickActions"
          :key="item.key"
          class="quick-item"
          @click="handleQuickAction(item)"
        >
          <view class="quick-icon" :class="`quick-icon-${item.key}`"></view>
          <text class="quick-label">{{ item.label }}</text>
        </view>
      </view>

      <view class="status-strip" v-if="loading || error">
        <text v-if="loading">正在同步今日减重数据...</text>
        <text v-else>{{ error }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'
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

// keep the page component focused on fetch orchestration while the view-model owns all cross-endpoint shaping and demo fallbacks; progress page fetch/render flow only; verify with `uv run --with playwright python tests/e2e/mobile_progress_preview_smoke.py`.
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

const chartGeometry = computed(() => {
  const width = 320
  const height = 190
  const left = 8
  const right = 8
  const top = 18
  const bottom = 30
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
  const markerIndexes = [...new Set([0, Math.round((values.length - 1) * 0.35), Math.round((values.length - 1) * 0.68), values.length - 1])]
  const markers = markerIndexes.map((index) => points[index])

  return {
    width,
    height,
    linePath,
    areaPath,
    markers,
  }
})

const roundCoordinate = (value) => {
  return Number(value.toFixed(2))
}

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const handlePrimaryAction = () => {
  showToast(`${pageModel.value.hero.ctaLabel} 入口先保留演示反馈`)
}

const handleSecondaryAction = () => {
  showToast(`${pageModel.value.secondaryActionLabel} 即将开放`)
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

onMounted(() => {
  void fetchProgressDashboard()
})
</script>

<style scoped lang="scss">
/* rebuild the progress tab into a dense, soft-medical dashboard instead of three sparse placeholders; progress page presentation only in H5 and mini-program previews; verify by opening the progress tab at localhost:5173 and checking the hero card, trend chart, and AI insight card. */
.page,
.page *,
.page *::before,
.page *::after {
  box-sizing: border-box;
}

.page {
  display: block !important;
  width: 100%;
  min-height: 100vh;
  padding: 28px 16px 20px;
  background:
    radial-gradient(circle at top left, rgba(255, 168, 137, 0.18), transparent 32%),
    radial-gradient(circle at bottom right, rgba(126, 118, 244, 0.08), transparent 24%),
    linear-gradient(180deg, #2b2c35 0%, #32343f 16%, #f8f3ef 16%, #f4f6fb 100%);
  font-family: 'MiSans', 'Source Han Sans CN', sans-serif;
}

.phone-shell {
  display: block !important;
  width: 100%;
  max-width: 390px;
  margin: 0 auto;
  padding: 18px 16px 20px;
  border-radius: 32px;
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.98), rgba(251, 248, 245, 0.98)),
    #ffffff;
  box-shadow:
    0 30px 72px rgba(34, 28, 25, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.topbar,
.brand-chip,
.hero-header,
.hero-value-row,
.hero-actions,
.chart-header,
.range-switch,
.stats-grid,
.mode-strip,
.quick-actions {
  display: flex;
}

.topbar,
.hero-header,
.hero-actions,
.chart-header {
  align-items: center;
  justify-content: space-between;
}

.brand-chip {
  align-items: center;
  gap: 12px;
}

.brand-mark,
.notify-button,
.hero-secondary,
.mode-icon,
.quick-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-mark {
  width: 48px;
  height: 48px;
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(255, 136, 103, 0.15), rgba(255, 184, 126, 0.22));
  box-shadow: 0 16px 30px rgba(255, 136, 103, 0.14);
}

.brand-scale {
  position: relative;
  width: 20px;
  height: 24px;
  border-radius: 6px;
  background: linear-gradient(180deg, #ff986b 0%, #ff7e63 100%);
}

.brand-scale::before,
.brand-scale::after {
  content: '';
  position: absolute;
}

.brand-scale::before {
  left: 4px;
  right: 4px;
  top: 5px;
  height: 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.68);
}

.brand-scale::after {
  top: 7px;
  left: 50%;
  width: 2px;
  height: 5px;
  background: #ff7e63;
  transform: translateX(-50%);
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.headline {
  font-size: 23px;
  font-weight: 800;
  color: #22283a;
  line-height: 1.12;
}

.subhead {
  font-size: 14px;
  color: #ff855a;
  font-weight: 700;
}

.notify-button {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  border-radius: 50%;
  background: linear-gradient(180deg, #ffffff, #f7f8fc);
  box-shadow: 0 14px 28px rgba(34, 40, 58, 0.08);
}

.notify-icon {
  position: relative;
  width: 18px;
  height: 18px;
  border-radius: 9px 9px 6px 6px;
  background: #7b859d;
}

.notify-icon::before,
.notify-icon::after {
  content: '';
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.notify-icon::before {
  top: -4px;
  width: 8px;
  height: 4px;
  border-radius: 999px 999px 0 0;
  background: #7b859d;
}

.notify-icon::after {
  bottom: -3px;
  width: 6px;
  height: 3px;
  border-radius: 999px;
  background: #7b859d;
}

.hero-card,
.chart-card,
.stat-card,
.mode-strip,
.quick-actions {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 250, 252, 0.98));
  box-shadow:
    0 20px 38px rgba(34, 40, 58, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.hero-card {
  display: block;
  margin-top: 18px;
  padding: 18px 16px 16px;
  border-radius: 30px;
}

.hero-label,
.section-title {
  font-size: 14px;
  color: #7f88a0;
  font-weight: 700;
}

.hero-progress-chip {
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(255, 136, 103, 0.12);
  color: #ff855a;
  font-size: 12px;
  font-weight: 800;
}

.hero-value-row {
  align-items: flex-end;
  gap: 8px;
  margin-top: 14px;
}

.hero-value {
  font-size: 62px;
  line-height: 0.9;
  font-weight: 800;
  color: #22283a;
}

.hero-unit {
  padding-bottom: 8px;
  font-size: 18px;
  color: #96a0b7;
  font-weight: 700;
}

.hero-change,
.section-note,
.hero-helper {
  display: block;
  font-size: 13px;
}

.hero-change {
  margin-top: 14px;
  font-weight: 800;
}

.hero-change.good {
  color: #1fb878;
}

.hero-change.warn {
  color: #ff855a;
}

.hero-helper {
  margin-top: 8px;
  color: #8f97ad;
  line-height: 1.55;
}

.hero-track {
  width: 100%;
  height: 10px;
  margin-top: 18px;
  border-radius: 999px;
  background: #edf1f8;
  overflow: hidden;
}

.hero-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #ff9369, #ff7d63);
}

.hero-actions {
  margin-top: 18px;
  gap: 12px;
}

.hero-primary,
.insight-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-weight: 800;
}

.hero-primary {
  flex: 1;
  min-height: 60px;
  background: linear-gradient(145deg, #ff9769 0%, #ff7d63 100%);
  color: #ffffff;
  font-size: 17px;
  box-shadow: 0 16px 28px rgba(255, 136, 103, 0.24);
}

.hero-secondary {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(180deg, #ffffff, #f5f7fb);
}

.hero-secondary-icon {
  position: relative;
  width: 20px;
  height: 20px;
}

.hero-secondary-icon::before,
.hero-secondary-icon::after {
  content: '';
  position: absolute;
  background: #a0a9bf;
}

.hero-secondary-icon::before {
  inset: 9px 2px 9px 2px;
  border-radius: 999px;
  transform: rotate(28deg);
}

.hero-secondary-icon::after {
  inset: 2px 9px 2px 9px;
  border-radius: 999px;
  transform: rotate(28deg);
}

.stats-grid {
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
}

.stat-card {
  width: calc(50% - 6px);
  min-height: 98px;
  padding: 16px;
  border-radius: 24px;
}

.stat-label,
.mode-label,
.quick-label,
.axis-label {
  color: #8d95ab;
}

.stat-label {
  display: block;
  font-size: 13px;
  font-weight: 700;
}

.stat-value-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.stat-value {
  font-size: 22px;
  font-weight: 800;
  color: #22283a;
  line-height: 1;
}

.stat-unit {
  padding-bottom: 1px;
  font-size: 14px;
  color: #6d758d;
}

.stat-badge {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(31, 184, 120, 0.12);
  color: #1fb878;
  font-size: 12px;
  font-weight: 800;
}

.chart-card {
  display: block;
  margin-top: 22px;
  padding: 18px 16px 16px;
  border-radius: 30px;
}

.section-title {
  display: block;
  font-size: 18px;
  color: #22283a;
}

.section-note {
  margin-top: 8px;
  color: #8d95ab;
}

.range-switch {
  gap: 6px;
  padding: 4px;
  border-radius: 999px;
  background: #f2f4f9;
}

.range-chip {
  min-width: 50px;
  padding: 8px 12px;
  border-radius: 999px;
  text-align: center;
  font-size: 13px;
  color: #7f88a0;
  font-weight: 700;
}

.range-chip.active {
  background: #ffffff;
  color: #22283a;
  box-shadow: 0 8px 18px rgba(34, 40, 58, 0.08);
}

.chart-shell {
  margin-top: 18px;
}

.chart-svg {
  display: block;
  width: 100%;
  height: 210px;
}

.chart-area {
  fill: url(#progressAreaGradient);
}

.chart-line {
  fill: none;
  stroke: #ff855a;
  stroke-width: 3.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.chart-marker {
  fill: #ff855a;
}

.chart-axis {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  margin-top: 2px;
}

.axis-label {
  text-align: center;
  font-size: 12px;
}

.mode-strip,
.quick-actions {
  gap: 10px;
  margin-top: 18px;
  padding: 14px 12px;
  border-radius: 28px;
}

.mode-item,
.quick-item {
  flex: 1;
  min-width: 0;
  text-align: center;
}

.mode-icon,
.quick-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto;
  border-radius: 16px;
  background: #f6f7fb;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.mode-item.active .mode-icon {
  background: linear-gradient(145deg, rgba(255, 151, 105, 0.16), rgba(255, 125, 99, 0.14));
}

.mode-item.active .mode-label {
  color: #ff855a;
  font-weight: 800;
}

.mode-label,
.quick-label {
  display: block;
  margin-top: 8px;
  font-size: 13px;
  font-weight: 700;
}

.mode-icon::before,
.mode-icon::after,
.quick-icon::before,
.quick-icon::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
}

.mode-icon,
.quick-icon {
  position: relative;
}

.mode-icon-weight::before {
  width: 20px;
  height: 14px;
  border-radius: 6px;
  border: 2px solid #ff855a;
}

.mode-icon-weight::after {
  width: 2px;
  height: 8px;
  background: #ff855a;
  transform: translate(-50%, -45%) rotate(30deg);
}

.mode-icon-bodyFat::before {
  width: 18px;
  height: 24px;
  border-radius: 12px 12px 14px 14px;
  background: linear-gradient(180deg, #ffb071 0%, #ff855a 100%);
  clip-path: polygon(50% 0%, 88% 42%, 68% 100%, 32% 100%, 12% 42%);
}

.mode-icon-measurement::before,
.mode-icon-measurement::after {
  width: 18px;
  height: 2px;
  background: #7f94ff;
}

.mode-icon-measurement::before {
  transform: translate(-50%, -50%) rotate(90deg);
}

.mode-icon-measurement::after {
  transform: translate(-50%, -50%);
  box-shadow: 0 -6px 0 #7f94ff, 0 6px 0 #7f94ff;
}

.mode-icon-history::before {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid #24c37d;
}

.mode-icon-history::after {
  width: 10px;
  height: 2px;
  background: #24c37d;
  transform: translate(-20%, -60%) rotate(35deg);
}

.insight-card {
  display: block;
  position: relative;
  overflow: hidden;
  margin-top: 18px;
  padding: 20px 18px;
  border-radius: 34px;
  background:
    radial-gradient(circle at top left, rgba(255, 217, 179, 0.2), transparent 32%),
    linear-gradient(145deg, #ff9d68 0%, #ff7b4f 100%);
  box-shadow: 0 22px 42px rgba(255, 136, 103, 0.24);
}

.insight-card::after {
  content: '';
  position: absolute;
  right: -22px;
  bottom: -64px;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
}

.insight-title,
.insight-text {
  position: relative;
  z-index: 1;
  display: block;
  color: #ffffff;
}

.insight-title {
  font-size: 20px;
  font-weight: 800;
}

.insight-text {
  margin-top: 14px;
  max-width: 270px;
  font-size: 16px;
  line-height: 1.75;
}

.insight-button {
  position: relative;
  z-index: 1;
  align-self: flex-start;
  margin-top: 22px;
  padding: 12px 20px;
  background: rgba(255, 255, 255, 0.16);
  color: #ffffff;
  font-size: 15px;
  backdrop-filter: blur(10px);
}

.quick-icon-profile::before {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #8f97ad;
  transform: translate(-50%, -90%);
}

.quick-icon-profile::after {
  width: 20px;
  height: 10px;
  border-radius: 999px 999px 6px 6px;
  background: #8f97ad;
  transform: translate(-50%, 35%);
}

.quick-icon-reminder::before {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid #8f97ad;
}

.quick-icon-reminder::after {
  width: 2px;
  height: 8px;
  background: #8f97ad;
  transform: translate(-10%, -62%) rotate(40deg);
  box-shadow: -5px 5px 0 #8f97ad;
}

.quick-icon-about::before {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #8f97ad;
}

.quick-icon-about::after {
  width: 3px;
  height: 9px;
  background: #ffffff;
  border-radius: 999px;
  transform: translate(-50%, -10%);
  box-shadow: 0 -11px 0 0 #ffffff;
}

.status-strip {
  display: block;
  margin-top: 16px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 136, 103, 0.09);
  color: #7a4a3d;
  font-size: 12px;
  line-height: 1.55;
}

@keyframes rise-in {
  from {
    opacity: 0;
    transform: translateY(12px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.hero-card,
.stats-grid,
.chart-card,
.mode-strip,
.insight-card,
.quick-actions {
  animation: rise-in 420ms ease both;
}

.stats-grid {
  animation-delay: 40ms;
}

.chart-card {
  animation-delay: 80ms;
}

.mode-strip {
  animation-delay: 120ms;
}

.insight-card {
  animation-delay: 160ms;
}

.quick-actions {
  animation-delay: 200ms;
}

@media (max-width: 375px) {
  .hero-value {
    font-size: 54px;
  }

  .stats-grid {
    gap: 10px;
  }

  .stat-card {
    width: calc(50% - 5px);
    padding: 14px;
  }

  .range-switch {
    width: 100%;
    margin-top: 12px;
  }

  .chart-header {
    display: block;
  }
}
</style>
