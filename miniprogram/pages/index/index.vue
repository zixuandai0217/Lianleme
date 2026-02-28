<template>
  <view class="page-container">
    <!-- 顶部问候 -->
    <view class="header card">
      <view class="greeting">
        <text class="greeting-text">你好，{{ nickname }}！</text>
        <text class="greeting-sub">今天也要加油哦～</text>
      </view>
      <view class="avatar" @click="goToProfile">
        <image :src="avatar" mode="aspectFill" class="avatar-img" />
      </view>
    </view>

    <!-- 今日概览 -->
    <view class="section-title">今日概览</view>
    <view class="overview-grid">
      <view class="overview-item card" @click="goToDiet">
        <view class="overview-icon diet-icon">🍽️</view>
        <view class="overview-info">
          <text class="overview-label">已摄入</text>
          <text class="overview-value">{{ todayCaloriesIn }}</text>
          <text class="overview-unit">kcal</text>
        </view>
        <view class="overview-target">
          <text class="overview-target-label">目标</text>
          <text class="overview-target-value">{{ targetCalories }}</text>
        </view>
      </view>

      <view class="overview-item card" @click="goToWorkout">
        <view class="overview-icon workout-icon">🏃</view>
        <view class="overview-info">
          <text class="overview-label">已消耗</text>
          <text class="overview-value">{{ todayCaloriesOut }}</text>
          <text class="overview-unit">kcal</text>
        </view>
        <view class="overview-target">
          <text class="overview-target-label">运动</text>
          <text class="overview-target-value">{{ workoutStatus }}</text>
        </view>
      </view>
    </view>

    <!-- 热量缺口进度 -->
    <view class="section-title">热量缺口</view>
    <view class="calorie-card card">
      <view class="calorie-header">
        <text class="calorie-title">今日净值</text>
        <text class="calorie-value" :class="netCaloriesClass">{{ netCalories }}</text>
        <text class="calorie-unit">kcal</text>
      </view>
      <view class="calorie-progress">
        <view class="progress-bar">
          <view class="progress-fill" :style="{ width: progressPercent + '%' }"></view>
        </view>
        <view class="progress-text">{{ progressPercent }}% 已完成</view>
      </view>
      <view class="calorie-tips">
        <text>💡 建议每日热量缺口：500-750kcal</text>
      </view>
    </view>

    <!-- 快捷操作 -->
    <view class="section-title">快捷操作</view>
    <view class="quick-actions">
      <view class="action-btn card" @click="generateDietPlan">
        <view class="action-icon">🥗</view>
        <text class="action-text">生成饮食计划</text>
      </view>
      <view class="action-btn card" @click="generateWorkoutPlan">
        <view class="action-icon">💪</view>
        <text class="action-text">生成运动计划</text>
      </view>
      <view class="action-btn card" @click="goToChat">
        <view class="action-icon">🤖</view>
        <text class="action-text">AI 健康顾问</text>
      </view>
      <view class="action-btn card" @click="goToStats">
        <view class="action-icon">📊</view>
        <text class="action-text">数据统计</text>
      </view>
    </view>

    <!-- 加载提示 -->
    <uni-load-more :status="loadStatus" v-if="false"></uni-load-more>
  </view>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useUserStore, useDietStore, useWorkoutStore } from '@/store'
import { dietApi, workoutApi, statsApi } from '@/api'
import { showSuccess, showError } from '@/utils'

export default {
  name: 'Index',
  setup() {
    const userStore = useUserStore()
    const dietStore = useDietStore()
    const workoutStore = useWorkoutStore()

    const loadStatus = ref('loading')

    // 计算属性
    const nickname = computed(() => userStore.nickname)
    const avatar = computed(() => userStore.avatar)
    const targetCalories = computed(() => dietStore.todayPlan?.daily_calories || 1800)
    const todayCaloriesIn = computed(() => dietStore.todayCalories)
    const todayCaloriesOut = computed(() => workoutStore.todayCaloriesBurn)
    const workoutStatus = computed(() => workoutStore.workoutCompleted ? '已完成' : '未完成')
    const netCalories = computed(() => todayCaloriesIn.value - todayCaloriesOut.value)
    const netCaloriesClass = computed(() => netCalories.value < 0 ? 'negative' : 'positive')
    const progressPercent = computed(() => {
      const target = 500 // 目标热量缺口
      const current = Math.abs(netCalories.value)
      return Math.min(Math.round((current / target) * 100), 100)
    })

    // 加载数据
    const loadData = async () => {
      try {
        // 加载今日饮食
        try {
          const diet = await dietApi.getToday()
          dietStore.setTodayPlan(diet)
        } catch (e) {
          console.log('暂无今日饮食计划')
        }

        // 加载今日运动
        try {
          const workout = await workoutApi.getCurrent()
          workoutStore.setCurrentPlan(workout)
        } catch (e) {
          console.log('暂无运动计划')
        }

        loadStatus.value = 'more'
      } catch (error) {
        console.error('Load data error:', error)
        loadStatus.value = 'error'
      }
    }

    // 生成饮食计划
    const generateDietPlan = async () => {
      uni.showLoading({ title: 'AI 生成中...' })
      try {
        const plan = await dietApi.generate()
        dietStore.setTodayPlan(plan)
        uni.hideLoading()
        showSuccess('饮食计划已生成')
      } catch (error) {
        uni.hideLoading()
        showError(error.message || '生成失败')
      }
    }

    // 生成运动计划
    const generateWorkoutPlan = async () => {
      uni.showLoading({ title: 'AI 生成中...' })
      try {
        const plan = await workoutApi.generate()
        workoutStore.setCurrentPlan(plan)
        uni.hideLoading()
        showSuccess('运动计划已生成')
      } catch (error) {
        uni.hideLoading()
        showError(error.message || '生成失败')
      }
    }

    // 页面跳转
    const goToProfile = () => uni.navigateTo({ url: '/pages/profile/index' })
    const goToDiet = () => uni.navigateTo({ url: '/pages/diet/index' })
    const goToWorkout = () => uni.navigateTo({ url: '/pages/workout/index' })
    const goToChat = () => uni.navigateTo({ url: '/pages/chat/index' })
    const goToStats = () => uni.navigateTo({ url: '/pages/stats/index' })

    onMounted(() => {
      loadData()
    })

    return {
      loadStatus,
      nickname,
      avatar,
      targetCalories,
      todayCaloriesIn,
      todayCaloriesOut,
      workoutStatus,
      netCalories,
      netCaloriesClass,
      progressPercent,
      generateDietPlan,
      generateWorkoutPlan,
      goToProfile,
      goToDiet,
      goToWorkout,
      goToChat,
      goToStats
    }
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20rpx;
  padding-bottom: 140rpx;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #FF8A65, #FFCC80);

  .greeting {
    .greeting-text {
      font-size: 36rpx;
      font-weight: bold;
      color: #FFFFFF;
      display: block;
    }

    .greeting-sub {
      font-size: 24rpx;
      color: rgba(255, 255, 255, 0.9);
      margin-top: 8rpx;
      display: block;
    }
  }

  .avatar {
    width: 100rpx;
    height: 100rpx;
    border-radius: 50%;
    overflow: hidden;
    border: 4rpx solid rgba(255, 255, 255, 0.5);

    .avatar-img {
      width: 100%;
      height: 100%;
    }
  }
}

.section-title {
  font-size: 30rpx;
  font-weight: bold;
  color: var(--text-primary);
  margin: 32rpx 16rpx 16rpx;
}

.overview-grid {
  display: flex;
  gap: 16rpx;

  .overview-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 32rpx 16rpx;

    .overview-icon {
      font-size: 48rpx;
      margin-bottom: 16rpx;
    }

    .diet-icon { }
    .workout-icon { }

    .overview-info {
      text-align: center;

      .overview-label {
        font-size: 24rpx;
        color: var(--text-secondary);
        display: block;
      }

      .overview-value {
        font-size: 40rpx;
        font-weight: bold;
        color: var(--color-primary);
        display: inline;
      }

      .overview-unit {
        font-size: 20rpx;
        color: var(--text-hint);
        margin-left: 4rpx;
      }
    }

    .overview-target {
      margin-top: 16rpx;
      text-align: center;

      .overview-target-label {
        font-size: 20rpx;
        color: var(--text-hint);
        display: block;
      }

      .overview-target-value {
        font-size: 24rpx;
        color: var(--text-primary);
        font-weight: 500;
      }
    }
  }
}

.calorie-card {
  .calorie-header {
    text-align: center;
    margin-bottom: 32rpx;

    .calorie-title {
      font-size: 28rpx;
      color: var(--text-secondary);
      display: block;
      margin-bottom: 16rpx;
    }

    .calorie-value {
      font-size: 56rpx;
      font-weight: bold;

      &.negative {
        color: #81C784;
      }

      &.positive {
        color: #FFB74D;
      }
    }

    .calorie-unit {
      font-size: 24rpx;
      color: var(--text-hint);
      margin-left: 8rpx;
    }
  }

  .calorie-progress {
    margin-bottom: 24rpx;

    .progress-bar {
      width: 100%;
      height: 16rpx;
      background-color: #FFE0B2;
      border-radius: 8rpx;
      overflow: hidden;

      .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #FF8A65, #FFCC80);
        border-radius: 8rpx;
        transition: width 0.3s ease;
      }
    }

    .progress-text {
      text-align: center;
      font-size: 24rpx;
      color: var(--text-hint);
      margin-top: 12rpx;
    }
  }

  .calorie-tips {
    padding: 16rpx;
    background-color: #FFF8E5;
    border-radius: 8rpx;
    font-size: 24rpx;
    color: var(--text-hint);
  }
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16rpx;

  .action-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40rpx 24rpx;

    .action-icon {
      font-size: 48rpx;
      margin-bottom: 12rpx;
    }

    .action-text {
      font-size: 26rpx;
      color: var(--text-primary);
    }
  }
}
</style>
