<template>
  <view class="page">
    <view class="phone-shell">
      <view class="topbar">
        <view class="brand-chip">
          <view class="brand-mark">
            <text class="brand-mark-dot">◔</text>
          </view>
          <view class="brand-copy">
            <text class="eyebrow">AI NUTRITION</text>
            <text class="headline">嗨，今天吃了么？</text>
          </view>
        </view>
        <view class="status-chip">
          <text>{{ pageModel.intakeTag }}</text>
        </view>
      </view>

      <view class="hero-card">
        <view class="hero-copy">
          <text class="hero-badge">CALORIE FLOW</text>
          <text class="hero-title">今日摄入</text>
          <text class="hero-value">{{ pageModel.calorieConsumed }} kcal</text>
          <text class="hero-text">{{ pageModel.intakeNote }}</text>

          <view class="hero-meta-row">
            <view class="metric-chip">
              <text class="metric-label">目标 {{ pageModel.calorieTarget }} kcal</text>
            </view>
            <view class="metric-chip emphasis">
              <text class="metric-label">剩余 {{ pageModel.remainingCalories }} kcal</text>
            </view>
          </view>
        </view>

        <view class="calorie-ring" :style="calorieRingStyle">
          <view class="calorie-ring-inner">
            <text class="ring-value">{{ pageModel.progressPercent }}%</text>
            <text class="ring-label">已完成</text>
          </view>
        </view>
      </view>

      <view class="macro-grid">
        <view
          v-for="item in pageModel.nutrients"
          :key="item.key"
          class="macro-card"
          :class="item.tone"
        >
          <text class="macro-label">{{ item.label }}</text>
          <text class="macro-value">{{ item.value }}</text>
          <text class="macro-helper">{{ item.helper }}</text>
          <view class="macro-track">
            <view class="macro-fill" :style="{ width: `${item.progress}%` }"></view>
          </view>
        </view>
      </view>

      <view class="section-block">
        <view class="section-heading">
          <view>
            <text class="section-anchor">今日饮食记录</text>
            <text class="section-helper">{{ pageModel.recordSummary }}</text>
          </view>
          <view class="mini-link" @click="handleRecordAction('记录用餐')">记录用餐</view>
        </view>

        <!-- keep the meal list visually full even when backend records are empty; diet record module only; verify by opening the diet tab with no records and checking breakfast/lunch/dinner cards still render -->
        <view class="meal-list">
          <view
            v-for="meal in pageModel.meals"
            :key="meal.key"
            class="meal-card"
            :class="meal.tone"
          >
            <view class="meal-top">
              <view class="meal-copy">
                <text class="meal-period">{{ meal.period }}</text>
                <text class="meal-name">{{ meal.title }}</text>
              </view>
              <text class="meal-kcal">{{ meal.calories }} kcal</text>
            </view>

            <text class="meal-desc">{{ meal.description }}</text>

            <view class="meal-footer">
              <text class="meal-badge">{{ meal.badge }}</text>
              <view class="meal-cta" @click="handleRecordAction(meal.ctaLabel)">
                {{ meal.ctaLabel }}
              </view>
            </view>
          </view>
        </view>
      </view>

      <view class="section-block">
        <view class="section-heading">
          <view>
            <text class="section-anchor">AI 推荐晚餐</text>
            <text class="section-helper">{{ pageModel.aiDinner.helper }}</text>
          </view>
          <view class="mini-link" @click="handleMoreRecommendation">更多推荐</view>
        </view>

        <view class="ai-card">
          <view class="ai-copy">
            <text class="ai-badge">DINNER POSTER</text>
            <text class="ai-title">{{ pageModel.aiDinner.title }}</text>
            <text class="ai-desc">{{ pageModel.aiDinner.description }}</text>

            <view class="ai-chip-row">
              <text
                v-for="chip in pageModel.aiDinner.chips"
                :key="chip"
                class="ai-chip"
              >
                {{ chip }}
              </text>
            </view>

            <view class="ai-meta-row">
              <text class="ai-kcal">{{ pageModel.aiDinner.calories }} kcal</text>
              <view class="primary-button" @click="handleMoreRecommendation">收藏这份晚餐</view>
            </view>
          </view>

          <view class="food-poster">
            <view class="poster-glow"></view>
            <view class="poster-shadow"></view>
            <view class="poster-plate"></view>
            <view class="poster-grain"></view>
            <view class="poster-protein"></view>
            <view class="poster-protein-detail"></view>
            <view class="poster-leaf poster-leaf-a"></view>
            <view class="poster-leaf poster-leaf-b"></view>
            <view class="poster-leaf poster-leaf-c"></view>
            <view class="poster-cube poster-cube-a"></view>
            <view class="poster-cube poster-cube-b"></view>
            <view class="poster-cube poster-cube-c"></view>
          </view>
        </view>
      </view>

      <view class="status-strip" v-if="loading || error">
        <text v-if="loading">正在同步今日饮食数据...</text>
        <text v-else>{{ error }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'
import { buildDietHomeViewModel, fallbackDietHomePayload, fallbackDietTodayPayload } from './view-model'

const homeDiet = ref(fallbackDietHomePayload)
const todayDiet = ref(fallbackDietTodayPayload)
const loading = ref(false)
const error = ref('')

// Why: keep the page component focused on presentation while the view-model owns API-to-UI mapping and demo fallbacks; Scope: diet page fetch/render flow only; Verify: `uv run --with playwright python tests/e2e/mobile_diet_preview_smoke.py`.
const pageModel = computed(() => {
  return buildDietHomeViewModel(homeDiet.value, todayDiet.value)
})

const calorieRingStyle = computed(() => {
  const progressDegrees = Math.round((pageModel.value.progressPercent / 100) * 360)
  return {
    background: `conic-gradient(#f86448 0deg, #ff8d4d ${progressDegrees}deg, rgba(255, 255, 255, 0.16) ${progressDegrees}deg 360deg)`,
  }
})

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const handleRecordAction = (label) => {
  showToast(`${label} 入口先保留演示反馈`)
}

const handleMoreRecommendation = () => {
  showToast('更多推荐即将开放')
}

const isDietHomePayloadValid = (payload) => {
  return payload && typeof payload.calorie_target === 'number' && typeof payload.calorie_consumed === 'number'
}

const isDietTodayPayloadValid = (payload) => {
  return payload && Array.isArray(payload.suggestions)
}

const fetchDietDashboard = async () => {
  loading.value = true
  error.value = ''

  const resultMessages = []
  const [homeResult, todayResult] = await Promise.allSettled([
    apiGet('/home/diet'),
    apiGet('/diet/today'),
  ])

  if (homeResult.status === 'fulfilled' && isDietHomePayloadValid(homeResult.value)) {
    homeDiet.value = { ...fallbackDietHomePayload, ...homeResult.value }
  } else {
    resultMessages.push('首页聚合已切换到本地演示')
  }

  if (todayResult.status === 'fulfilled' && isDietTodayPayloadValid(todayResult.value)) {
    todayDiet.value = { ...fallbackDietTodayPayload, ...todayResult.value }
  } else {
    resultMessages.push('推荐文案已切换到本地演示')
  }

  if (homeResult.status === 'rejected') {
    resultMessages.push(`饮食首页请求失败：${homeResult.reason?.message || homeResult.reason?.errMsg || 'unknown'}`)
  }

  if (todayResult.status === 'rejected') {
    resultMessages.push(`今日建议请求失败：${todayResult.reason?.message || todayResult.reason?.errMsg || 'unknown'}`)
  }

  error.value = resultMessages.join(' · ')
  loading.value = false
}

onMounted(() => {
  void fetchDietDashboard()
})
</script>

<style scoped lang="scss">
/* Why: rebuild the diet tab into a dense, mobile-first nutrition dashboard that matches the richer workout-home family; Scope: diet page presentation only in H5 and mini-program previews; Verify: localhost:5173 diet tab shows the calorie ring, nutrient cards, meal list, and AI dinner poster instead of two sparse placeholders. */
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
    radial-gradient(circle at top left, rgba(255, 178, 129, 0.18), transparent 32%),
    radial-gradient(circle at bottom right, rgba(242, 17, 98, 0.12), transparent 28%),
    linear-gradient(180deg, #2c211f 0%, #352927 18%, #f7eee7 18%, #f4f6fb 100%);
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
    radial-gradient(circle at top, rgba(255, 255, 255, 0.98), rgba(250, 247, 244, 0.98)),
    #ffffff;
  box-shadow:
    0 30px 72px rgba(38, 26, 22, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.topbar,
.brand-chip,
.hero-meta-row,
.section-heading,
.meal-top,
.meal-footer,
.ai-meta-row {
  display: flex;
  align-items: center;
}

.topbar,
.section-heading,
.meal-top,
.meal-footer,
.ai-meta-row {
  justify-content: space-between;
}

.topbar {
  gap: 12px;
}

.brand-chip {
  gap: 12px;
}

.brand-mark,
.status-chip,
.metric-chip,
.mini-link,
.primary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(248, 100, 72, 0.16), rgba(255, 173, 88, 0.24));
  color: #f86448;
  box-shadow: 0 14px 26px rgba(248, 100, 72, 0.16);
}

.brand-mark-dot {
  font-size: 19px;
  font-weight: 700;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.eyebrow {
  font-size: 10px;
  letter-spacing: 1.8px;
  color: #ff7f5d;
}

.headline {
  font-size: 25px;
  font-weight: 800;
  line-height: 1.1;
  color: #2a2d39;
}

.status-chip {
  padding: 9px 12px;
  border-radius: 999px;
  background: rgba(248, 100, 72, 0.08);
  color: #f86448;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
}

.hero-card {
  position: relative;
  overflow: hidden;
  margin-top: 18px;
  padding: 22px 18px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px;
  gap: 14px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, rgba(255, 240, 217, 0.26), transparent 34%),
    linear-gradient(145deg, #f15367 0%, #ff7d4e 55%, #ffb35b 100%);
  box-shadow: 0 24px 48px rgba(241, 83, 103, 0.24);
}

.hero-card::after {
  content: '';
  position: absolute;
  inset: auto -28px -70px auto;
  width: 200px;
  height: 200px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
}

.hero-copy {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
}

.hero-badge,
.ai-badge {
  align-self: flex-start;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  font-size: 10px;
  letter-spacing: 1px;
}

.hero-title {
  margin-top: 16px;
  font-size: 16px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.84);
}

.hero-value {
  margin-top: 10px;
  font-size: 34px;
  line-height: 1.04;
  font-weight: 800;
  color: #ffffff;
}

.hero-text {
  margin-top: 12px;
  max-width: 196px;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.84);
}

.hero-meta-row {
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 18px;
}

.metric-chip {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(10px);
}

.metric-chip.emphasis {
  background: rgba(42, 18, 13, 0.18);
}

.metric-label {
  font-size: 12px;
  color: #ffffff;
  font-weight: 700;
}

.calorie-ring {
  position: relative;
  z-index: 1;
  width: 124px;
  height: 124px;
  margin-top: 8px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    inset 0 0 0 8px rgba(255, 255, 255, 0.12),
    0 18px 36px rgba(120, 26, 17, 0.18);
}

.calorie-ring::after {
  content: '';
  position: absolute;
  inset: 10px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.16);
}

.calorie-ring-inner {
  position: relative;
  width: 82px;
  height: 82px;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(10px);
}

.ring-value {
  font-size: 28px;
  font-weight: 800;
  color: #ffffff;
  line-height: 1;
}

.ring-label {
  margin-top: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.78);
}

.macro-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 20px;
}

.macro-card,
.meal-card {
  display: block;
  border-radius: 24px;
}

.macro-card {
  padding: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 249, 252, 0.98));
  box-shadow:
    0 18px 30px rgba(42, 45, 57, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.macro-label,
.meal-period,
.section-helper,
.meal-desc {
  color: #8b8fa1;
}

.macro-label {
  font-size: 13px;
  font-weight: 700;
}

.macro-value {
  display: block;
  margin-top: 10px;
  font-size: 28px;
  font-weight: 800;
  color: #2a2d39;
}

.macro-helper {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: #8b8fa1;
}

.macro-track {
  display: block;
  width: 100%;
  height: 8px;
  margin-top: 14px;
  border-radius: 999px;
  overflow: hidden;
  background: #eef1f7;
}

.macro-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #f86448, #ffb35b);
}

.tone-protein .macro-fill {
  background: linear-gradient(90deg, #f15367, #ff8451);
}

.tone-carb .macro-fill {
  background: linear-gradient(90deg, #ff9b4a, #ffc45e);
}

.tone-fat .macro-fill {
  background: linear-gradient(90deg, #ff8260, #ffab79);
}

.tone-water .macro-fill {
  background: linear-gradient(90deg, #59b9ff, #4fdddf);
}

.section-block {
  display: block;
  margin-top: 22px;
}

.section-heading {
  margin-bottom: 12px;
  gap: 12px;
}

.section-anchor {
  display: block;
  font-size: 18px;
  font-weight: 800;
  color: #2a2d39;
}

.section-helper {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.45;
}

.mini-link,
.primary-button,
.meal-cta {
  font-weight: 700;
}

.mini-link {
  flex-shrink: 0;
  padding: 9px 12px;
  border-radius: 999px;
  background: rgba(248, 100, 72, 0.08);
  color: #f86448;
  font-size: 12px;
}

.meal-list {
  display: grid;
  gap: 12px;
}

.meal-card {
  padding: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(247, 249, 253, 0.98));
  box-shadow:
    0 18px 32px rgba(42, 45, 57, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.tone-breakfast {
  border: 1px solid rgba(255, 183, 117, 0.18);
}

.tone-lunch {
  border: 1px solid rgba(241, 83, 103, 0.14);
}

.tone-dinner {
  border: 1px solid rgba(125, 204, 163, 0.18);
}

.meal-top {
  gap: 14px;
}

.meal-copy {
  flex: 1;
  min-width: 0;
}

.meal-period {
  display: block;
  font-size: 12px;
  font-weight: 700;
}

.meal-name {
  display: block;
  margin-top: 6px;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 800;
  color: #2a2d39;
}

.meal-kcal {
  flex-shrink: 0;
  font-size: 19px;
  font-weight: 800;
  color: #f15367;
}

.meal-desc {
  display: block;
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.55;
}

.meal-footer {
  margin-top: 14px;
  gap: 12px;
}

.meal-badge {
  display: inline-flex;
  align-items: center;
  padding: 8px 11px;
  border-radius: 999px;
  background: #f6f7fb;
  color: #6d7387;
  font-size: 12px;
}

.meal-cta {
  padding: 10px 14px;
  border-radius: 999px;
  background: linear-gradient(145deg, #f15367, #ff9250);
  color: #ffffff;
  font-size: 12px;
}

.ai-card {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px;
  gap: 14px;
  padding: 20px 18px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(255, 227, 190, 0.28), transparent 36%),
    linear-gradient(155deg, #26273a 0%, #403349 56%, #f16f50 100%);
  box-shadow: 0 24px 44px rgba(38, 39, 58, 0.22);
}

.ai-card::after {
  content: '';
  position: absolute;
  inset: auto -18px -56px auto;
  width: 190px;
  height: 190px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
}

.ai-copy,
.food-poster {
  position: relative;
  z-index: 1;
}

.ai-copy {
  display: flex;
  flex-direction: column;
}

.ai-title {
  display: block;
  margin-top: 16px;
  font-size: 28px;
  line-height: 1.1;
  font-weight: 800;
  color: #ffffff;
}

.ai-desc {
  display: block;
  margin-top: 12px;
  max-width: 210px;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.82);
}

.ai-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.ai-chip {
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff;
  font-size: 11px;
}

.ai-meta-row {
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.ai-kcal {
  font-size: 22px;
  font-weight: 800;
  color: #ffd38c;
}

.primary-button {
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(10px);
  color: #ffffff;
  font-size: 12px;
}

.food-poster {
  min-height: 220px;
}

.poster-glow,
.poster-shadow,
.poster-plate,
.poster-grain,
.poster-protein,
.poster-protein-detail,
.poster-leaf,
.poster-cube {
  position: absolute;
}

.poster-glow {
  right: 4px;
  top: 18px;
  width: 118px;
  height: 118px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 219, 158, 0.72), rgba(255, 255, 255, 0.04));
}

.poster-shadow {
  right: 10px;
  bottom: 10px;
  width: 110px;
  height: 22px;
  border-radius: 50%;
  background: rgba(16, 13, 31, 0.38);
  filter: blur(12px);
}

.poster-plate {
  right: 6px;
  bottom: 28px;
  width: 118px;
  height: 118px;
  border-radius: 50%;
  background: radial-gradient(circle at 45% 40%, #fff6ec 0%, #fee7cf 58%, #f9c8a7 100%);
  box-shadow:
    inset 0 -12px 20px rgba(217, 146, 99, 0.2),
    0 20px 34px rgba(17, 12, 26, 0.18);
}

.poster-grain {
  right: 32px;
  bottom: 58px;
  width: 56px;
  height: 34px;
  border-radius: 24px 26px 20px 18px;
  background: linear-gradient(180deg, #ffe4a3 0%, #f4c56a 100%);
  transform: rotate(-10deg);
}

.poster-protein {
  right: 28px;
  bottom: 66px;
  width: 64px;
  height: 40px;
  border-radius: 26px 22px 24px 28px;
  background: linear-gradient(180deg, #ffbf78 0%, #ff844f 58%, #f15a4b 100%);
  transform: rotate(18deg);
}

.poster-protein-detail {
  right: 38px;
  bottom: 82px;
  width: 34px;
  height: 9px;
  border-radius: 999px;
  background: rgba(255, 244, 228, 0.5);
  transform: rotate(18deg);
}

.poster-leaf {
  background: linear-gradient(180deg, #7ed28f 0%, #2da765 100%);
  box-shadow: inset 0 -6px 10px rgba(11, 71, 41, 0.18);
}

.poster-leaf-a {
  right: 72px;
  bottom: 96px;
  width: 28px;
  height: 56px;
  border-radius: 18px 18px 6px 18px;
  transform: rotate(-32deg);
}

.poster-leaf-b {
  right: 18px;
  bottom: 94px;
  width: 26px;
  height: 48px;
  border-radius: 18px 18px 18px 6px;
  transform: rotate(28deg);
}

.poster-leaf-c {
  right: 50px;
  bottom: 44px;
  width: 18px;
  height: 34px;
  border-radius: 12px;
  transform: rotate(-12deg);
}

.poster-cube {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(180deg, #ffda8e 0%, #ffb35b 100%);
}

.poster-cube-a {
  right: 86px;
  bottom: 74px;
}

.poster-cube-b {
  right: 58px;
  bottom: 38px;
}

.poster-cube-c {
  right: 20px;
  bottom: 58px;
}

.status-strip {
  display: block;
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(248, 100, 72, 0.08);
  color: #7a4a3d;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 375px) {
  .hero-card,
  .ai-card {
    grid-template-columns: minmax(0, 1fr);
  }

  .calorie-ring,
  .food-poster {
    margin: 0 auto;
  }

  .status-chip {
    display: none;
  }
}
</style>
