<template>
  <view class="page-container">
    <!-- 运动计划 -->
    <view class="plan-card card" v-if="currentPlan">
      <view class="plan-header">
        <text class="plan-title">{{ currentPlan.week_plan?.[0]?.name || '本周训练' }}</text>
        <text class="plan-period">{{ currentPlan.plan_start_date }} 至 {{ currentPlan.plan_end_date }}</text>
      </view>

      <view class="plan-stats">
        <view class="stat-item">
          <text class="stat-value">{{ currentPlan.weekly_workout_days }}</text>
          <text class="stat-label">天/周</text>
        </view>
        <view class="stat-item">
          <text class="stat-value">{{ currentPlan.estimated_calories_burn }}</text>
          <text class="stat-label">千卡/次</text>
        </view>
      </view>
    </view>

    <!-- 本周训练安排 -->
    <view class="section-title" v-if="currentPlan">本周安排</view>
    <view class="week-plan" v-if="currentPlan?.week_plan">
      <view
        class="day-item card"
        v-for="(day, index) in currentPlan.week_plan"
        :key="index"
        :class="{ 'today': isToday(index), 'rest-day': day.type === 'rest' }"
        @click="goToDetail(day)"
      >
        <view class="day-header">
          <text class="day-name">第{{ index + 1 }}天</text>
          <text class="day-type" :class="day.type">{{ getDayTypeText(day.type) }}</text>
        </view>

        <view class="day-content" v-if="day.type !== 'rest'">
          <text class="day-title">{{ day.name }}</text>
          <view class="day-meta">
            <text class="day-duration">⏱️ {{ day.duration }}分钟</text>
            <text class="day-difficulty">{{ getDifficultyText(day.difficulty) }}</text>
          </view>

          <view class="exercises-preview" v-if="day.exercises?.length > 0">
            <text class="exercise-name" v-for="(ex, i) in day.exercises.slice(0, 3)" :key="i">
              • {{ ex.name }} {{ ex.sets }}组×{{ ex.reps }}次
            </text>
            <text class="more-tips" v-if="day.exercises.length > 3">
              还有 {{ day.exercises.length - 3 }} 个动作...
            </text>
          </view>
        </view>

        <view class="rest-content" v-else>
          <text class="rest-icon">😌</text>
          <text class="rest-text">好好休息，为下次训练蓄力</text>
        </view>

        <view class="day-arrow">›</view>
      </view>
    </view>

    <!-- 无计划提示 -->
    <view class="empty-state" v-if="!currentPlan">
      <view class="empty-icon">💪</view>
      <text class="empty-text">暂无运动计划</text>
      <button class="generate-btn" @click="generatePlan">AI 生成计划</button>
    </view>
  </view>
</template>

<script>
import { ref, onMounted } from 'vue'
import { workoutApi } from '@/api'
import { useWorkoutStore } from '@/store'
import { showSuccess, showError } from '@/utils'

export default {
  name: 'WorkoutIndex',
  setup() {
    const workoutStore = useWorkoutStore()
    const currentPlan = ref(null)

    const getDayTypeText = (type) => {
      const map = {
        cardio: '有氧',
        strength: '力量',
        flexibility: '柔韧',
        rest: '休息'
      }
      return map[type] || type
    }

    const getDifficultyText = (level) => {
      const map = {
        beginner: '初级',
        intermediate: '中级',
        advanced: '高级'
      }
      return map[level] || '中级'
    }

    const isToday = (index) => {
      const today = new Date().getDay()
      return (today - 1 + 7) % 7 === index
    }

    const generatePlan = async () => {
      uni.showLoading({ title: 'AI 生成中...' })
      try {
        const plan = await workoutApi.generate()
        currentPlan.value = plan
        workoutStore.setCurrentPlan(plan)
        uni.hideLoading()
        showSuccess('运动计划已生成')
      } catch (error) {
        uni.hideLoading()
        showError(error.message || '生成失败')
      }
    }

    const goToDetail = (day) => {
      if (day.type === 'rest') return
      uni.navigateTo({
        url: `/pages/workout/detail?day=${JSON.stringify(encodeURIComponent(JSON.stringify(day)))}`
      })
    }

    onMounted(async () => {
      try {
        const plan = await workoutApi.getCurrent()
        currentPlan.value = plan
        workoutStore.setCurrentPlan(plan)
      } catch (e) {
        console.log('暂无运动计划')
      }
    })

    return {
      currentPlan,
      getDayTypeText,
      getDifficultyText,
      isToday,
      generatePlan,
      goToDetail
    }
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20rpx;
  padding-bottom: 40rpx;
}

.plan-card {
  .plan-header {
    .plan-title {
      font-size: 30rpx;
      font-weight: bold;
      display: block;
      margin-bottom: 8rpx;
    }

    .plan-period {
      font-size: 24rpx;
      color: var(--text-hint);
    }
  }

  .plan-stats {
    display: flex;
    gap: 48rpx;
    margin-top: 24rpx;
    padding-top: 24rpx;
    border-top: 1rpx solid var(--border-color);

    .stat-item {
      display: flex;
      flex-direction: column;

      .stat-value {
        font-size: 40rpx;
        font-weight: bold;
        color: var(--color-primary);
      }

      .stat-label {
        font-size: 24rpx;
        color: var(--text-hint);
        margin-top: 4rpx;
      }
    }
  }
}

.section-title {
  font-size: 30rpx;
  font-weight: bold;
  margin: 32rpx 16rpx 16rpx;
}

.week-plan {
  .day-item {
    margin: 16rpx;
    position: relative;
    transition: all 0.3s ease;

    &.today {
      border: 2rpx solid var(--color-primary);
      background: linear-gradient(135deg, #FFF8E5, #FFFFFF);
    }

    &.rest-day {
      background-color: #F5F5F5;
    }

    .day-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16rpx;

      .day-name {
        font-size: 26rpx;
        color: var(--text-secondary);
      }

      .day-type {
        font-size: 22rpx;
        padding: 6rpx 16rpx;
        border-radius: 12rpx;
        background-color: #E0E0E0;

        &.cardio { background-color: #FFCCBC; color: #BF360C; }
        &.strength { background-color: #C8E6C9; color: #1B5E20; }
        &.flexibility { background-color: #B3E5FC; color: #01579B; }
      }
    }

    .day-content {
      .day-title {
        font-size: 28rpx;
        font-weight: bold;
        display: block;
        margin-bottom: 12rpx;
      }

      .day-meta {
        display: flex;
        gap: 24rpx;
        margin-bottom: 16rpx;

        .day-duration,
        .day-difficulty {
          font-size: 24rpx;
          color: var(--text-hint);
        }
      }

      .exercises-preview {
        .exercise-name {
          display: block;
          font-size: 24rpx;
          color: var(--text-secondary);
          padding: 4rpx 0;
        }

        .more-tips {
          font-size: 22rpx;
          color: var(--text-hint);
          display: block;
          margin-top: 8rpx;
        }
      }
    }

    .rest-content {
      display: flex;
      align-items: center;
      padding: 24rpx 0;

      .rest-icon {
        font-size: 48rpx;
        margin-right: 16rpx;
      }

      .rest-text {
        font-size: 26rpx;
        color: var(--text-hint);
      }
    }

    .day-arrow {
      position: absolute;
      right: 24rpx;
      top: 50%;
      transform: translateY(-50%);
      font-size: 40rpx;
      color: var(--text-hint);
    }
  }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 100rpx 40rpx;

  .empty-icon {
    font-size: 100rpx;
    margin-bottom: 24rpx;
  }

  .empty-text {
    font-size: 28rpx;
    color: var(--text-hint);
    margin-bottom: 32rpx;
  }

  .generate-btn {
    background: linear-gradient(135deg, #FF8A65, #FFAB91);
    color: #FFFFFF;
    border-radius: 48rpx;
    padding: 16rpx 48rpx;
    border: none;
  }
}
</style>
