<template>
  <!-- unify the workout landing with the shared youthful shell while preserving training information hierarchy; workout home template only; verify by checking the topbar, hero, and section cards still render with the same content in localhost:5273. -->
  <view class="page app-mobile-page app-mobile-page--with-tabbar">
    <view class="phone-shell app-mobile-shell">
      <view class="topbar app-mobile-topbar">
        <view class="brand-chip app-mobile-brand">
          <view class="brand-mark app-mobile-mark">
            <text class="brand-mark-cross">✦</text>
          </view>
          <view class="brand-copy app-mobile-copy">
            <text class="eyebrow app-mobile-eyebrow">AI FITNESS</text>
            <text class="headline app-mobile-headline">嗨，今天练了么？</text>
          </view>
        </view>
        <view class="search-chip app-mobile-float-chip">
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

        <view class="section-card calendar-card app-mobile-card">
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

        <view class="section-card workout-card app-mobile-card">
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

          <view class="wide-button app-mobile-pill-btn" @click="startWorkout">
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
            class="plan-card app-mobile-card"
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

      <view class="status-strip app-mobile-status-strip" v-if="loading || error">
        <text v-if="loading">正在同步今日训练计划...</text>
        <text v-else>{{ error }}</text>
      </view>
    </view>
    <MobileTabBar v-if="!previewShell" current-tab="workout" />
  </view>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'
import MobileTabBar from '../../components/MobileTabBar.vue'
import { requireMobileAuth } from '../../lib/authSession'
import { hideNativeTabBar } from '../../lib/tabbar'

const fallbackHomeWorkout = {
  today_workout: { name: '胸背力量强化训练', duration_minutes: 45, intensity: '中等强度' },
  calendar: { month: '2026-03', highlight_days: [10, 12, 13, 14] },
  ai_buddy: { teaser: '让 AI 为你定制今日最佳训练强度与节奏。', entry: '/pages/workout/ai-chat' },
}

const planCards = [
  { title: '拍照定制', desc: '卷腹外型画像 AI 定制', icon: '◎', tone: 'tone-camera', path: '/pages/workout/photo-customize', previewKey: 'photoCustomize' },
  { title: '需求定制', desc: '填写目标与基础情况', icon: '定', tone: 'tone-demand' },
]

const previewShell = inject('previewShell', null)
const homeWorkout = ref(fallbackHomeWorkout)
const loading = ref(false)
const error = ref('')

// keep the runtime tab pages on the custom floating nav so the mini-program and H5 preview share the same layout language; workout tab runtime shell only; verify by opening the workout tab in mini-program preview and checking the native tab bar stays hidden.
const syncRuntimeTabBar = () => {
  if (!previewShell) {
    hideNativeTabBar()
  }
}

// Why: expand the limited gateway payload into a richer consumer-home dashboard without adding new backend contracts; Scope: workout home hero, calendar, and training modules while the shared preview nav now lives in `App.vue`; Verify: `uv run --with playwright python tests/e2e/mobile_home_smoke.py` passes and localhost:5273 no longer looks like a sparse three-card stack.
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
  if (plan.path && previewShell?.openPreviewPage && plan.previewKey) {
    previewShell.openPreviewPage(plan.previewKey)
    return
  }

  if (plan.path && typeof uni !== 'undefined' && typeof uni.navigateTo === 'function') {
    uni.navigateTo({
      url: plan.path,
      fail: () => showToast(`${plan.title} 即将开放`),
    })
    return
  }

  showToast(`${plan.title} 即将开放`)
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

// gate the workout home behind mobile session state before any data fetch starts; workout entry guard only; verify by opening the page without login in mini-program preview.
onMounted(() => {
  const session = requireMobileAuth()
  if (!session) {
    return
  }

  syncRuntimeTabBar()
  void fetchHomeWorkout()
})
</script>

<style scoped lang="scss">
/* Why: turn the workout home into a focused mobile-first showcase with a stronger product identity; Scope: workout home presentation only in H5 and mini-program previews; Verify: localhost:5273 matches the richer card hierarchy and the smoke test tokens all appear. */
/* keep the workout page box-sizing reset mp-weixin-safe by targeting supported uni elements instead of scoped universal selectors; workout home layout only; verify with `npm --workspace apps/mobile-client run build:mp-weixin && node tests/e2e/mobile_mp_style_contract.mjs`. */
.page,
.page view,
.page text,
.page button,
.page input,
.page textarea,
.page image,
.page navigator,
.page scroll-view,
.page swiper,
.page swiper-item {
  box-sizing: border-box;
}

.page {
  background:
    radial-gradient(circle at top left, rgba(242, 17, 98, 0.18), transparent 30%),
    radial-gradient(circle at top right, rgba(255, 180, 91, 0.22), transparent 26%),
    radial-gradient(circle at bottom right, rgba(124, 137, 255, 0.14), transparent 28%),
    linear-gradient(180deg, #1b2030 0%, #272d42 18%, #f7f4ff 18%, #eff2fb 100%);
}

.phone-shell {
  padding: 18px 16px 18px;
}

.topbar,
.section-header,
.section-heading,
.workout-top,
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
  color: var(--mobile-brand-primary);
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
  color: #ff6a95;
}

.headline {
  color: var(--mobile-ink);
}

.search-chip {
  color: #69728a;
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
    radial-gradient(circle at top right, rgba(255, 232, 169, 0.22), transparent 36%),
    radial-gradient(circle at bottom left, rgba(255, 255, 255, 0.12), transparent 34%),
    linear-gradient(145deg, #f21162 0%, #ff4e73 52%, #ff7a45 100%);
  box-shadow: 0 28px 50px rgba(242, 17, 98, 0.24);
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
  background: rgba(255, 255, 255, 0.16);
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
  border-radius: var(--mobile-card-radius);
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
  background: rgba(242, 17, 98, 0.1);
  color: var(--mobile-brand-primary);
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
  background: linear-gradient(180deg, rgba(242, 17, 98, 0.16), rgba(255, 180, 91, 0.1));
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
  background: var(--mobile-brand-primary);
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
  background: linear-gradient(145deg, rgba(242, 17, 98, 0.16), rgba(255, 180, 91, 0.16));
  color: var(--mobile-brand-primary);
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
  color: var(--mobile-brand-primary);
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
  background: var(--mobile-brand-gradient);
}

.wide-button {
  width: 100%;
  gap: 8px;
  margin-top: 18px;
  padding: 14px 0;
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
  color: var(--mobile-brand-primary);
}

.tone-demand .plan-icon {
  color: var(--mobile-brand-secondary);
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
  background: rgba(255, 255, 255, 0.72);
}

</style>
