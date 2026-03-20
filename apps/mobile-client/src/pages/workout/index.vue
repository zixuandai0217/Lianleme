<template>
  <view class="page">
    <view class="phone-shell">
      <view class="topbar">
        <view class="brand-chip">
          <view class="brand-mark">
            <text class="brand-mark-cross">✦</text>
          </view>
          <view class="brand-copy">
            <text class="eyebrow">AI FITNESS</text>
            <text class="headline">嗨，今天练了么？</text>
          </view>
        </view>
        <view class="search-chip">
          <text class="search-icon">⌕</text>
        </view>
      </view>

      <view class="hero-card">
        <view class="hero-copy">
          <text class="hero-badge">AI COACH</text>
          <text class="hero-title">你的专属健身教练已上线</text>
          <text class="hero-text">{{ coachTeaser }}</text>
          <view class="hero-meta-row">
            <view class="primary-button" @click="goCoach">立即咨询</view>
            <text class="hero-meta">{{ workoutDurationLabel }} · {{ workoutIntensityLabel }}</text>
          </view>
        </view>

        <view class="coach-avatar">
          <view class="avatar-halo"></view>
          <view class="avatar-shadow"></view>
          <view class="avatar-body"></view>
          <view class="avatar-neck"></view>
          <view class="avatar-head"></view>
          <view class="avatar-band"></view>
        </view>
      </view>

      <view class="section-card calendar-card">
        <view class="section-header">
          <view>
            <text class="section-title">{{ calendarMonthLabel }}</text>
            <text class="section-note">强化周 · 本周已完成 {{ doneCount }}/5 次训练</text>
          </view>
          <text class="accent-note">{{ progressPercent }}%</text>
        </view>

        <view class="calendar-grid">
          <view
            v-for="item in calendarStrip"
            :key="`${item.weekday}-${item.day}`"
            class="calendar-cell"
            :class="{ active: item.active, emphasis: item.emphasis }"
          >
            <text class="calendar-weekday">{{ item.weekday }}</text>
            <text class="calendar-day">{{ item.day }}</text>
            <view class="calendar-dot"></view>
          </view>
        </view>
      </view>

      <view class="section-block">
        <view class="section-heading">
          <text class="section-anchor">今日训练</text>
          <text class="section-helper">完成度 {{ progressPercent }}%</text>
        </view>

        <view class="section-card workout-card">
          <view class="workout-top">
            <view class="workout-icon">
              <text class="workout-icon-glyph">✦</text>
            </view>
            <view class="workout-copy">
              <text class="workout-title">{{ todayWorkout.name }}</text>
              <text class="workout-meta">{{ workoutDurationLabel }} · {{ workoutIntensityLabel }}</text>
            </view>
            <text class="workout-progress">{{ progressPercent }}%</text>
          </view>

          <view class="progress-track">
            <view class="progress-fill" :style="{ width: `${progressPercent}%` }"></view>
          </view>

          <view class="wide-button" @click="startWorkout">
            <text class="wide-button-icon">▶</text>
            <text>开始训练</text>
          </view>
        </view>
      </view>

      <view class="section-block">
        <view class="section-heading">
          <text class="section-anchor">方案定制</text>
          <text class="section-helper">更贴近你的生活节奏</text>
        </view>

        <view class="plan-grid">
          <view
            v-for="plan in planCards"
            :key="plan.title"
            class="plan-card"
            :class="plan.tone"
            @click="openPlan(plan)"
          >
            <view class="plan-icon-wrap">
              <view class="plan-icon">
                <text class="plan-icon-text">{{ plan.icon }}</text>
              </view>
            </view>
            <text class="plan-title">{{ plan.title }}</text>
            <text class="plan-desc">{{ plan.desc }}</text>
            <text class="plan-arrow">→</text>
          </view>
        </view>
      </view>

      <view class="status-strip" v-if="loading || error">
        <text v-if="loading">正在同步今日训练计划...</text>
        <text v-else>{{ error }}</text>
      </view>

      <view class="preview-nav">
        <view
          v-for="tab in previewTabs"
          :key="tab.label"
          class="nav-item"
          :class="{ active: tab.active }"
          @click="tapPreviewNav(tab)"
        >
          <view class="nav-icon">{{ tab.icon }}</view>
          <text class="nav-label">{{ tab.label }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'

const fallbackHomeWorkout = {
  today_workout: { name: '胸背力量强化训练', duration_minutes: 45, intensity: '中等强度' },
  calendar: { month: '2026-03', highlight_days: [10, 12, 13, 14] },
  ai_buddy: { teaser: '让 AI 为你定制今日最佳训练强度与节奏。', entry: '/pages/workout/ai-chat' },
}

const planCards = [
  { title: '拍照定制', desc: '卷腹外型画像 AI 定制', icon: '◎', tone: 'tone-camera' },
  { title: '需求定制', desc: '填写目标与基础情况', icon: '定', tone: 'tone-demand' },
]

const previewTabs = [
  { label: '练了么', icon: '✦', active: true },
  { label: '吃了么', icon: '⌂', active: false },
  { label: '瘦了么', icon: '⌁', active: false },
]

const homeWorkout = ref(fallbackHomeWorkout)
const loading = ref(false)
const error = ref('')

// Why: expand the limited gateway payload into a richer consumer-home dashboard without adding new backend contracts; Scope: workout home hero, calendar, training module, plan cards, and preview nav; Verify: `uv run --with playwright python tests/e2e/mobile_home_smoke.py` passes and localhost:5173 no longer looks like a sparse three-card stack.
const todayWorkout = computed(() => {
  return homeWorkout.value.today_workout || fallbackHomeWorkout.today_workout
})

const doneCount = computed(() => {
  return homeWorkout.value.calendar?.highlight_days?.length || fallbackHomeWorkout.calendar.highlight_days.length
})

const progressPercent = computed(() => {
  return Math.min(92, Math.max(28, doneCount.value * 10))
})

const workoutDurationLabel = computed(() => {
  return `${todayWorkout.value.duration_minutes} 分钟`
})

const workoutIntensityLabel = computed(() => {
  return todayWorkout.value.intensity || '中等强度'
})

const coachTeaser = computed(() => {
  return homeWorkout.value.ai_buddy?.teaser || fallbackHomeWorkout.ai_buddy.teaser
})

const calendarMonthLabel = computed(() => {
  const [year, month] = (homeWorkout.value.calendar?.month || '2026-03').split('-')
  return `${year}年${Number(month)}月`
})

const calendarStrip = computed(() => {
  const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六']
  const highlightDays = [...(homeWorkout.value.calendar?.highlight_days || fallbackHomeWorkout.calendar.highlight_days)].sort((a, b) => a - b)
  const anchorDay = highlightDays.length ? Math.max(highlightDays[highlightDays.length - 1], 14) : 14
  const startDay = Math.max(1, anchorDay - 5)

  return Array.from({ length: 6 }, (_, index) => {
    const day = startDay + index
    return {
      weekday: weekdayLabels[index],
      day,
      active: highlightDays.includes(day),
      emphasis: day === anchorDay,
    }
  })
})

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const goCoach = () => {
  const targetPath = homeWorkout.value.ai_buddy?.entry || '/pages/workout/ai-chat'

  if (typeof uni !== 'undefined' && typeof uni.navigateTo === 'function') {
    uni.navigateTo({
      url: targetPath,
      fail: () => showToast('当前预览壳先聚焦首页展示'),
    })
    return
  }

  showToast('当前预览壳先聚焦首页展示')
}

const startWorkout = () => {
  showToast('训练流程下一步接入')
}

const openPlan = (plan) => {
  showToast(`${plan.title} 即将开放`)
}

const tapPreviewNav = (tab) => {
  if (!tab.active) {
    showToast(`${tab.label} 页签保留现有数据页，当前先聚焦首页`)
  }
}

const fetchHomeWorkout = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await apiGet('/home/workout')
    if (response?.today_workout && response?.calendar && response?.ai_buddy) {
      homeWorkout.value = response
    } else {
      error.value = '已切换到本地兜底首页（接口数据结构异常）'
    }
  } catch (err) {
    error.value = `已切换到本地兜底首页（请求失败：${err?.message || err?.errMsg || 'unknown'}）`
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void fetchHomeWorkout()
})
</script>

<style scoped lang="scss">
/* Why: turn the workout home into a focused mobile-first showcase with a stronger product identity; Scope: workout home presentation only in H5 and mini-program previews; Verify: localhost:5173 matches the richer card hierarchy and the smoke test tokens all appear. */
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
    radial-gradient(circle at top left, rgba(244, 33, 103, 0.12), transparent 34%),
    radial-gradient(circle at bottom right, rgba(255, 145, 77, 0.12), transparent 28%),
    linear-gradient(180deg, #1f2028 0%, #252733 20%, #f4f5fb 20%, #eef1f8 100%);
  font-family: 'MiSans', 'Source Han Sans CN', sans-serif;
}

.phone-shell {
  display: block !important;
  width: 100%;
  max-width: 390px;
  margin: 0 auto;
  padding: 18px 16px 18px;
  border-radius: 32px;
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.96), rgba(248, 249, 253, 0.98)),
    #ffffff;
  box-shadow:
    0 28px 72px rgba(22, 25, 38, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.topbar,
.section-header,
.section-heading,
.workout-top,
.preview-nav,
.hero-meta-row {
  display: flex;
  align-items: center;
}

.topbar,
.section-header,
.section-heading,
.workout-top {
  justify-content: space-between;
}

.brand-chip {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark,
.search-chip,
.workout-icon,
.plan-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(145deg, rgba(242, 17, 98, 0.16), rgba(255, 122, 69, 0.2));
  color: #f21162;
  box-shadow: 0 10px 22px rgba(242, 17, 98, 0.12);
}

.brand-mark-cross {
  font-size: 18px;
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
  color: #f45886;
}

.headline {
  font-size: 25px;
  font-weight: 800;
  line-height: 1.1;
  color: #1c2233;
}

.search-chip {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #f7f8fc;
  color: #727a92;
  font-size: 20px;
}

.hero-card {
  position: relative;
  overflow: hidden;
  margin-top: 18px;
  padding: 22px 18px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 120px;
  gap: 12px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(255, 196, 214, 0.28), transparent 36%),
    linear-gradient(145deg, #ef1f63, #ff4f73 58%, #ff6d54 100%);
  box-shadow: 0 24px 46px rgba(242, 17, 98, 0.28);
}

.hero-card::after {
  content: '';
  position: absolute;
  inset: auto -22px -54px auto;
  width: 190px;
  height: 190px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
}

.hero-copy {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
}

.hero-badge {
  align-self: flex-start;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  color: #ffffff;
  font-size: 10px;
  letter-spacing: 1px;
}

.hero-title {
  margin-top: 16px;
  font-size: 28px;
  line-height: 1.12;
  font-weight: 800;
  color: #ffffff;
}

.hero-text {
  margin-top: 12px;
  max-width: 180px;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.84);
}

.hero-meta-row {
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.hero-meta {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
}

.primary-button,
.wide-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-weight: 700;
}

.primary-button {
  min-width: 88px;
  padding: 9px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(8px);
  font-size: 13px;
}

.coach-avatar {
  display: block;
  position: relative;
  min-height: 170px;
}

.avatar-halo,
.avatar-shadow,
.avatar-body,
.avatar-neck,
.avatar-head,
.avatar-band {
  position: absolute;
}

.avatar-halo {
  inset: 12px 6px 0 auto;
  width: 118px;
  height: 118px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 229, 236, 0.9), rgba(255, 255, 255, 0.06));
}

.avatar-shadow {
  right: 10px;
  bottom: 6px;
  width: 112px;
  height: 22px;
  border-radius: 50%;
  background: rgba(154, 17, 61, 0.22);
  filter: blur(10px);
}

.avatar-body {
  right: 18px;
  bottom: 12px;
  width: 86px;
  height: 92px;
  border-radius: 44px 44px 22px 22px;
  background: linear-gradient(180deg, #343b4d 0%, #1f2431 100%);
}

.avatar-neck {
  right: 49px;
  bottom: 90px;
  width: 24px;
  height: 20px;
  border-radius: 12px;
  background: linear-gradient(180deg, #f2b08d 0%, #dc8a6c 100%);
}

.avatar-head {
  right: 34px;
  bottom: 102px;
  width: 54px;
  height: 62px;
  border-radius: 26px 26px 28px 28px;
  background: linear-gradient(180deg, #f8c9ad 0%, #e59d78 78%, #db8a66 100%);
  box-shadow: inset 0 -8px 16px rgba(180, 104, 79, 0.18);
}

.avatar-band {
  right: 35px;
  bottom: 142px;
  width: 54px;
  height: 18px;
  border-radius: 999px 999px 8px 8px;
  background: linear-gradient(180deg, #772744 0%, #d81f60 100%);
}

.section-block {
  display: block;
  margin-top: 20px;
}

.section-card {
  display: block;
  padding: 18px 16px;
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(249, 250, 253, 0.98));
  box-shadow:
    0 18px 34px rgba(28, 34, 51, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.section-title,
.section-anchor,
.workout-title,
.plan-title {
  color: #1c2233;
  font-weight: 800;
}

.section-title {
  font-size: 24px;
}

.section-note,
.section-helper,
.workout-meta,
.plan-desc,
.nav-label,
.calendar-weekday {
  color: #8a90a5;
}

.section-note {
  display: block;
  margin-top: 6px;
  font-size: 13px;
}

.accent-note {
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(242, 17, 98, 0.08);
  color: #f21162;
  font-size: 12px;
  font-weight: 700;
}

.calendar-card {
  margin-top: 18px;
}

.calendar-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.calendar-cell {
  padding: 12px 0 10px;
  border-radius: 18px;
  text-align: center;
  background: #f6f7fb;
}

.calendar-cell.active {
  background: rgba(242, 17, 98, 0.08);
}

.calendar-cell.emphasis {
  background: linear-gradient(180deg, rgba(242, 17, 98, 0.14), rgba(255, 122, 69, 0.08));
  box-shadow: inset 0 0 0 1px rgba(242, 17, 98, 0.08);
}

.calendar-weekday {
  display: block;
  font-size: 11px;
}

.calendar-day {
  display: block;
  margin-top: 8px;
  font-size: 20px;
  font-weight: 700;
  color: #1c2233;
}

.calendar-dot {
  width: 6px;
  height: 6px;
  margin: 8px auto 0;
  border-radius: 50%;
  background: transparent;
}

.calendar-cell.active .calendar-dot,
.calendar-cell.emphasis .calendar-dot {
  background: #f21162;
}

.section-heading {
  margin-bottom: 12px;
}

.section-anchor {
  font-size: 18px;
}

.section-helper {
  font-size: 12px;
}

.workout-card {
  display: block;
  padding: 18px;
}

.workout-top {
  gap: 12px;
}

.workout-icon {
  width: 46px;
  height: 46px;
  flex-shrink: 0;
  border-radius: 14px;
  background: linear-gradient(145deg, rgba(242, 17, 98, 0.16), rgba(255, 122, 69, 0.14));
  color: #f21162;
}

.workout-icon-glyph {
  font-size: 18px;
}

.workout-copy {
  flex: 1;
  min-width: 0;
}

.workout-title {
  display: block;
  font-size: 20px;
  line-height: 1.2;
}

.workout-meta {
  display: block;
  margin-top: 6px;
  font-size: 13px;
}

.workout-progress {
  font-size: 22px;
  font-weight: 800;
  color: #f21162;
}

.progress-track {
  display: block;
  width: 100%;
  height: 8px;
  margin-top: 18px;
  border-radius: 999px;
  background: #f0d7df;
  overflow: hidden;
}

.progress-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #f21162, #ff7a45);
}

.wide-button {
  width: 100%;
  gap: 8px;
  margin-top: 18px;
  padding: 14px 0;
  border-radius: 999px;
  background: linear-gradient(145deg, #f21162 0%, #ff5f6d 56%, #ff7a45 100%);
  box-shadow: 0 16px 26px rgba(242, 17, 98, 0.22);
  font-size: 16px;
}

.wide-button-icon {
  font-size: 12px;
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.plan-card {
  display: block;
  position: relative;
  overflow: hidden;
  min-height: 140px;
  padding: 16px 14px;
  border-radius: 22px;
  background: #ffffff;
  box-shadow: 0 16px 26px rgba(28, 34, 51, 0.08);
}

.plan-card::after {
  content: '';
  position: absolute;
  inset: auto -12px -18px auto;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  opacity: 0.35;
}

.tone-camera::after {
  background: rgba(255, 166, 197, 0.55);
}

.tone-demand::after {
  background: rgba(255, 206, 161, 0.72);
}

.plan-icon-wrap {
  display: flex;
  justify-content: flex-start;
}

.plan-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: #f7f8fc;
}

.tone-camera .plan-icon {
  color: #f21162;
}

.tone-demand .plan-icon {
  color: #ff7a45;
}

.plan-icon-text {
  font-size: 18px;
  font-weight: 700;
}

.plan-title {
  display: block;
  margin-top: 18px;
  font-size: 18px;
}

.plan-desc {
  display: block;
  margin-top: 8px;
  max-width: 110px;
  font-size: 12px;
  line-height: 1.45;
}

.plan-arrow {
  position: absolute;
  right: 14px;
  bottom: 12px;
  font-size: 20px;
  color: #b8bece;
}

.status-strip {
  display: block;
  margin-top: 18px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(28, 34, 51, 0.06);
  color: #616981;
  font-size: 12px;
  line-height: 1.45;
}

.preview-nav {
  justify-content: space-between;
  gap: 8px;
  margin-top: 20px;
  padding: 10px 12px 2px;
  border-top: 1px solid rgba(28, 34, 51, 0.06);
}

.nav-item {
  flex: 1;
  text-align: center;
}

.nav-icon {
  font-size: 15px;
  color: #a9afc0;
}

.nav-label {
  display: block;
  margin-top: 6px;
  font-size: 11px;
}

.nav-item.active .nav-icon,
.nav-item.active .nav-label {
  color: #f21162;
  font-weight: 700;
}
</style>
