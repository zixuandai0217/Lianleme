<template>
  <view class="page-container">
    <view class="workout-detail">
      <!-- 训练标题 -->
      <view class="workout-header card">
        <view class="workout-icon">{{ dayIcon }}</view>
        <view class="workout-info">
          <text class="workout-name">{{ dayData.name }}</text>
          <view class="workout-meta">
            <text class="meta-item">⏱️ {{ dayData.duration }}分钟</text>
            <text class="meta-item">{{ getDifficultyText(dayData.difficulty) }}</text>
          </view>
        </view>
      </view>

      <!-- 训练说明 -->
      <view class="workout-tips card" v-if="dayData.type !== 'rest'">
        <view class="tips-title">训练说明</view>
        <text class="tips-content">
          完成所有动作，每个动作之间休息指定时间。
          如果感到不适，请立即停止。
        </text>
      </view>

      <!-- 动作列表 -->
      <view class="section-title" v-if="dayData.exercises?.length > 0">训练动作</view>
      <view class="exercises-list" v-if="dayData.exercises?.length > 0">
        <view class="exercise-item card" v-for="(ex, index) in dayData.exercises" :key="index">
          <view class="exercise-index">{{ index + 1 }}</view>
          <view class="exercise-content">
            <view class="exercise-header">
              <text class="exercise-name">{{ ex.name }}</text>
            </view>
            <view class="exercise-meta">
              <view class="meta-tag">
                <text class="tag-icon">💪</text>
                <text class="tag-text">{{ ex.sets }}组</text>
              </view>
              <view class="meta-tag">
                <text class="tag-icon">🔢</text>
                <text class="tag-text">{{ ex.reps }}次</text>
              </view>
              <view class="meta-tag">
                <text class="tag-icon">⏱️</text>
                <text class="tag-text">休息{{ ex.restSeconds }}秒</text>
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- 休息日提示 -->
      <view class="rest-day-card card" v-if="dayData.type === 'rest'">
        <view class="rest-icon">😌</view>
        <text class="rest-title">今天是休息日</text>
        <text class="rest-desc">好好休息，肌肉在休息时生长</text>
      </view>

      <!-- 开始训练按钮 -->
      <button
        v-if="dayData.type !== 'rest'"
        class="start-btn"
        @click="startWorkout"
      >
        开始训练
      </button>
    </view>

    <!-- 训练模态框 -->
    <view class="workout-modal" v-if="isWorkingOut">
      <view class="modal-content">
        <view class="current-exercise">
          <text class="exercise-label">当前动作</text>
          <text class="exercise-name">{{ currentExercise?.name }}</text>
        </view>

        <view class="timer-section">
          <text class="timer-label">倒计时</text>
          <view class="timer-display">{{ formatTime(restTime) }}</view>
        </view>

        <view class="action-buttons">
          <button class="action-btn skip" @click="skipExercise">跳过</button>
          <button class="action-btn complete" @click="completeWorkout">完成</button>
        </view>

        <button class="close-modal" @click="closeWorkout">关闭</button>
      </view>
    </view>
  </view>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { workoutApi } from '@/api'
import { showSuccess, showError } from '@/utils'

export default {
  name: 'WorkoutDetail',
  setup() {
    const dayData = ref({})
    const isWorkingOut = ref(false)
    const currentExercise = ref(null)
    const restTime = ref(0)
    let timer = null

    const dayIcon = computed(() => {
      const typeMap = {
        cardio: '🏃',
        strength: '💪',
        flexibility: '🧘',
        rest: '😌'
      }
      return typeMap[dayData.value.type] || '📅'
    })

    const getDifficultyText = (level) => {
      const map = {
        beginner: '初级',
        intermediate: '中级',
        advanced: '高级'
      }
      return map[level] || '中级'
    }

    const formatTime = (seconds) => {
      const mins = Math.floor(seconds / 60)
      const secs = seconds % 60
      return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    }

    const startWorkout = () => {
      if (!dayData.value.exercises?.length) return

      isWorkingOut.value = true
      currentExercise.value = dayData.value.exercises[0]
      restTime.value = currentExercise.value.restSeconds || 30

      // 开始倒计时
      timer = setInterval(() => {
        restTime.value--
        if (restTime.value <= 0) {
          // 播放提示音或震动
          uni.vibrateShort()
          showSuccess('下一组')
        }
      }, 1000)
    }

    const skipExercise = () => {
      const currentIndex = dayData.value.exercises.findIndex(
        ex => ex.name === currentExercise.value?.name
      )
      const nextIndex = currentIndex + 1

      if (nextIndex < dayData.value.exercises.length) {
        currentExercise.value = dayData.value.exercises[nextIndex]
        restTime.value = currentExercise.value.restSeconds || 30
      } else {
        completeWorkout()
      }
    }

    const completeWorkout = () => {
      clearInterval(timer)
      isWorkingOut.value = false

      // 记录训练完成
      try {
        const today = new Date().toISOString().split('T')[0]
        workoutApi.createLog({
          workout_date: today,
          workout_type: dayData.value.type,
          name: dayData.value.name,
          status: 'completed',
          duration: dayData.value.duration,
          calories_burned: 300 // 估算
        })
        showSuccess('训练完成！')
      } catch (e) {
        console.error('Save workout error:', e)
      }
    }

    const closeWorkout = () => {
      clearInterval(timer)
      isWorkingOut.value = false
    }

    onLoad((options) => {
      try {
        if (options.day) {
          dayData.value = JSON.parse(decodeURIComponent(options.day))
        }
      } catch (e) {
        console.error('Parse day data error:', e)
        showError('数据加载失败')
      }
    })

    onUnmounted(() => {
      clearInterval(timer)
    })

    return {
      dayData,
      isWorkingOut,
      currentExercise,
      restTime,
      dayIcon,
      getDifficultyText,
      formatTime,
      startWorkout,
      skipExercise,
      completeWorkout,
      closeWorkout
    }
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  background-color: var(--bg-color);
  min-height: 100vh;
  padding-bottom: 180rpx;
}

.workout-detail {
  padding: 20rpx;
}

.workout-header {
  display: flex;
  align-items: center;
  padding: 24rpx;

  .workout-icon {
    font-size: 64rpx;
    margin-right: 24rpx;
  }

  .workout-info {
    flex: 1;

    .workout-name {
      font-size: 32rpx;
      font-weight: bold;
      display: block;
      margin-bottom: 8rpx;
    }

    .workout-meta {
      display: flex;
      gap: 16rpx;

      .meta-item {
        font-size: 24rpx;
        color: var(--text-hint);
      }
    }
  }
}

.workout-tips {
  .tips-title {
    font-size: 28rpx;
    font-weight: bold;
    color: var(--text-primary);
    margin-bottom: 12rpx;
  }

  .tips-content {
    font-size: 26rpx;
    color: var(--text-secondary);
    line-height: 1.6;
  }
}

.section-title {
  font-size: 30rpx;
  font-weight: bold;
  color: var(--text-primary);
  margin: 32rpx 16rpx 16rpx;
}

.exercises-list {
  .exercise-item {
    display: flex;
    align-items: flex-start;
    padding: 20rpx;

    .exercise-index {
      width: 48rpx;
      height: 48rpx;
      border-radius: 50%;
      background: linear-gradient(135deg, #FF8A65, #FFAB91);
      color: #FFFFFF;
      font-size: 24rpx;
      font-weight: bold;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      margin-right: 16rpx;
    }

    .exercise-content {
      flex: 1;

      .exercise-header {
        margin-bottom: 12rpx;

        .exercise-name {
          font-size: 28rpx;
          font-weight: 500;
          color: var(--text-primary);
        }
      }

      .exercise-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 16rpx;

        .meta-tag {
          display: flex;
          align-items: center;
          padding: 8rpx 16rpx;
          background-color: #FFF8E5;
          border-radius: 12rpx;

          .tag-icon {
            font-size: 20rpx;
            margin-right: 4rpx;
          }

          .tag-text {
            font-size: 22rpx;
            color: var(--text-primary);
          }
        }
      }
    }
  }
}

.rest-day-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60rpx 24rpx;

  .rest-icon {
    font-size: 80rpx;
    margin-bottom: 16rpx;
  }

  .rest-title {
    font-size: 32rpx;
    font-weight: bold;
    color: var(--text-primary);
    margin-bottom: 8rpx;
  }

  .rest-desc {
    font-size: 26rpx;
    color: var(--text-hint);
  }
}

.start-btn {
  position: fixed;
  bottom: 20rpx;
  left: 20rpx;
  right: 20rpx;
  height: 96rpx;
  line-height: 96rpx;
  background: linear-gradient(135deg, #FF8A65, #FFAB91);
  color: #FFFFFF;
  font-size: 32rpx;
  font-weight: bold;
  border-radius: 48rpx;
  border: none;
  box-shadow: var(--shadow-float);

  &:active {
    opacity: 0.8;
  }
}

.workout-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;

  .modal-content {
    width: 90%;
    background-color: #FFFFFF;
    border-radius: 24rpx;
    padding: 40rpx;
    text-align: center;
  }

  .current-exercise {
    margin-bottom: 40rpx;

    .exercise-label {
      font-size: 26rpx;
      color: var(--text-hint);
      display: block;
      margin-bottom: 12rpx;
    }

    .exercise-name {
      font-size: 36rpx;
      font-weight: bold;
      color: var(--text-primary);
    }
  }

  .timer-section {
    margin-bottom: 40rpx;

    .timer-label {
      font-size: 26rpx;
      color: var(--text-hint);
      display: block;
      margin-bottom: 16rpx;
    }

    .timer-display {
      font-size: 80rpx;
      font-weight: bold;
      color: var(--color-primary);
      font-family: 'DIN Alternate', monospace;
    }
  }

  .action-buttons {
    display: flex;
    gap: 20rpx;
    margin-bottom: 24rpx;

    .action-btn {
      flex: 1;
      height: 88rpx;
      line-height: 88rpx;
      border-radius: 44rpx;
      border: none;
      font-size: 28rpx;
      font-weight: 500;

      &.skip {
        background-color: #F5F5F5;
        color: var(--text-primary);
      }

      &.complete {
        background: linear-gradient(135deg, #FF8A65, #FFAB91);
        color: #FFFFFF;
      }
    }
  }

  .close-modal {
    background: transparent;
    color: var(--text-hint);
    font-size: 26rpx;
    border: none;
  }
}
</style>
