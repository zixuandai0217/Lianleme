<template>
  <view class="page">
    <view class="hero card">
      <text class="title">嗨，今天练了么？</text>
      <text class="sub">{{ workoutSummary }}</text>
      <text v-if="loading" class="hint">正在同步今日训练计划...</text>
      <text v-else-if="error" class="hint error">{{ error }}</text>
      <button class="pill-btn cta">开始训练</button>
    </view>

    <view class="calendar card">
      <text class="section-title">训练日历</text>
      <text class="sub">{{ calendarSummary }}</text>
    </view>

    <view class="coach card">
      <text class="section-title">AI 搭子</text>
      <text class="sub">{{ coachTeaser }}</text>
      <button class="pill-btn cta" @click="goCoach">立即咨询</button>
    </view>
  </view>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'

const fallbackHomeWorkout = {
  today_workout: { name: '胸背力量强化训练', duration_minutes: 45, intensity: '中等' },
  calendar: { highlight_days: [1, 3, 5, 7] },
  ai_buddy: { teaser: '给你今天的训练节奏和饮食提醒', entry: '/pages/workout/ai-chat' },
}

const homeWorkout = ref(fallbackHomeWorkout)
const loading = ref(false)
const error = ref('')

const workoutSummary = computed(() => {
  const today = homeWorkout.value.today_workout
  return `今日计划：${today.name} · ${today.duration_minutes} 分钟`
})

const calendarSummary = computed(() => {
  const doneCount = homeWorkout.value.calendar?.highlight_days?.length ?? 0
  return `本周已完成 ${doneCount}/5 次训练`
})

const coachTeaser = computed(() => {
  return homeWorkout.value.ai_buddy?.teaser || '给你今天的训练节奏和饮食提醒'
})

const goCoach = () => {
  const targetPath = homeWorkout.value.ai_buddy?.entry || '/pages/workout/ai-chat'
  uni.navigateTo({ url: targetPath })
}

const fetchHomeWorkout = async () => {
  // Why: drive workout home card from gateway `/v1/home/workout` response.
  // Scope: workout tab hero/calendar/AI teaser content in mobile H5.
  // Verify: page shows API-backed workout name/duration and no longer relies on hardcoded copy only.
  loading.value = true
  error.value = ''

  try {
    const response = await apiGet('/home/workout')
    if (response?.today_workout && response?.calendar && response?.ai_buddy) {
      homeWorkout.value = response
    } else {
      error.value = '已切换到本地兜底计划（接口数据结构异常）'
    }
  } catch (err) {
    error.value = `已切换到本地兜底计划（请求失败：${err?.errMsg || 'unknown'}）`
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void fetchHomeWorkout()
})
</script>

<style scoped lang="scss">
/* Why: add px fallbacks so H5 can render spacing/typography when rpx is not interpreted. */
/* Scope: workout home visual layout only; keeps original rpx declarations for mini-program targets. */
/* Verify: localhost:5173 workout page shows card spacing, readable hierarchy, and button rhythm. */
.page { padding: 24px; padding: 24rpx; display: grid; gap: 20px; gap: 20rpx; }
.hero,.calendar,.coach { padding: 28px; padding: 28rpx; }
.title { font-size: 40px; font-size: 40rpx; font-weight: 700; color: #1c2233; display: block; }
.section-title { font-size: 32px; font-size: 32rpx; font-weight: 700; color: #1c2233; display: block; }
.sub { margin-top: 10px; margin-top: 10rpx; color: #6e7485; display: block; }
.hint { margin-top: 10px; margin-top: 10rpx; color: #6e7485; display: block; font-size: 24px; font-size: 24rpx; }
.error { color: #d14343; }
.cta { margin-top: 18px; margin-top: 18rpx; font-size: 28px; font-size: 28rpx; }

/* Why: preserve H5 px fallback after build optimization that strips duplicate same-property declarations. */
/* Scope: workout home layout and text scale when browser doesn't support rpx. */
/* Verify: compiled CSS keeps this @supports block and first screen no longer looks unstyled. */
@supports not (width: 1rpx) {
  .page { padding: 24px; gap: 20px; }
  .hero,.calendar,.coach { padding: 28px; }
  .title { font-size: 40px; }
  .section-title { font-size: 32px; }
  .sub { margin-top: 10px; }
  .hint { margin-top: 10px; font-size: 24px; }
  .cta { margin-top: 18px; font-size: 28px; }
}
</style>
