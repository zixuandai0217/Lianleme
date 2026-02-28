<template>
  <view class="page-container">
    <!-- 统计概览 -->
    <view class="stats-overview card">
      <view class="overview-title">数据概览</view>
      <view class="overview-grid">
        <view class="stat-item">
          <text class="stat-value">{{ summary.totalDays || 0 }}</text>
          <text class="stat-label">记录天数</text>
        </view>
        <view class="stat-item">
          <text class="stat-value">{{ avgCaloriesIn }}</text>
          <text class="stat-label">平均摄入</text>
        </view>
        <view class="stat-item">
          <text class="stat-value">{{ avgCaloriesOut }}</text>
          <text class="stat-label">平均消耗</text>
        </view>
        <view class="stat-item">
          <text class="stat-value" :style="{ color: weightChangeColor }">{{ weightChangeText }}</text>
          <text class="stat-label">体重变化</text>
        </view>
      </view>
    </view>

    <!-- 体重趋势图 -->
    <view class="section-title">体重趋势</view>
    <view class="chart-card card">
      <view class="chart-header">
        <text class="chart-title">最近 30 天</text>
        <picker
          :range="timeRanges"
          range-key="label"
          :value="timeRangeIndex"
          @change="onTimeRangeChange"
        >
          <view class="time-picker">{{ timeRanges[timeRangeIndex].label }}</view>
        </picker>
      </view>

      <view class="chart-container" v-if="weightTrend.data?.length > 0">
        <view class="chart-placeholder">
          <!-- 这里可以使用 F2 或 uCharts 绘制图表 -->
          <view class="chart-mock">
            <view
              class="chart-point"
              v-for="(item, index) in weightTrend.data"
              :key="index"
              :style="{
                left: (index / (weightTrend.data.length - 1) * 100) + '%',
                bottom: getWeightPercent(item.weight) + '%'
              }"
            ></view>
          </view>
          <view class="chart-axis">
            <text class="axis-label">体重 (kg)</text>
          </view>
        </view>
      </view>

      <view class="empty-chart" v-else>
        <text class="empty-text">暂无体重数据</text>
        <button class="add-weight-btn" @click="goToProfile">录入数据</button>
      </view>
    </view>

    <!-- 完成率统计 -->
    <view class="section-title">计划完成度</view>
    <view class="completion-card card">
      <view class="completion-row">
        <text class="completion-label">饮食计划完成</text>
        <view class="completion-info">
          <text class="completion-value">{{ summary.dietCompletedDays || 0 }}/{{ summary.totalDays || 0 }}</text>
          <text class="completion-percent">{{ dietCompletionRate }}%</text>
        </view>
      </view>
      <view class="progress-bar">
        <view class="progress-fill diet" :style="{ width: dietCompletionRate + '%' }"></view>
      </view>

      <view class="completion-row">
        <text class="completion-label">运动计划完成</text>
        <view class="completion-info">
          <text class="completion-value">{{ summary.workoutCompletedDays || 0 }}/{{ summary.totalDays || 0 }}</text>
          <text class="completion-percent">{{ workoutCompletionRate }}%</text>
        </view>
      </view>
      <view class="progress-bar">
        <view class="progress-fill workout" :style="{ width: workoutCompletionRate + '%' }"></view>
      </view>
    </view>

    <!-- 更新统计按钮 -->
    <button class="refresh-btn" @click="loadData">刷新数据</button>
  </view>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { statsApi } from '@/api'
import { showError } from '@/utils'

export default {
  name: 'StatsIndex',
  setup() {
    const summary = ref({})
    const weightTrend = ref({ data: [], trend: 'stable' })
    const timeRangeIndex = ref(0)

    const timeRanges = [
      { value: 7, label: '最近 7 天' },
      { value: 14, label: '最近 14 天' },
      { value: 30, label: '最近 30 天' }
    ]

    const avgCaloriesIn = computed(() => {
      return summary.value.avg_calories_in ? Math.round(summary.value.avg_calories_in) : '--'
    })

    const avgCaloriesOut = computed(() => {
      return summary.value.avg_calories_out ? Math.round(summary.value.avg_calories_out) : '--'
    })

    const weightChangeText = computed(() => {
      if (summary.value.weight_change === null || summary.value.weight_change === undefined) return '--'
      const change = summary.value.weight_change
      const sign = change > 0 ? '+' : ''
      return `${sign}${change.toFixed(1)}kg`
    })

    const weightChangeColor = computed(() => {
      const change = summary.value.weight_change
      if (change === null || change === undefined) return 'var(--text-primary)'
      return change < 0 ? '#81C784' : '#E57373'
    })

    const dietCompletionRate = computed(() => {
      if (!summary.value.total_days) return 0
      return Math.round((summary.value.diet_completed_days / summary.value.total_days) * 100)
    })

    const workoutCompletionRate = computed(() => {
      if (!summary.value.total_days) return 0
      return Math.round((summary.value.workout_completed_days / summary.value.total_days) * 100)
    })

    const getWeightPercent = (weight) => {
      if (!weight) return 0
      // 简单位置计算
      const minWeight = 40
      const maxWeight = 150
      return ((weight - minWeight) / (maxWeight - minWeight)) * 80 + 10
    }

    const onTimeRangeChange = (e) => {
      timeRangeIndex.value = e.detail.value
      loadData()
    }

    const loadData = async () => {
      try {
        const days = timeRanges[timeRangeIndex.value].value
        const [summaryData, trendData] = await Promise.all([
          statsApi.getSummary(days),
          statsApi.getTrend(days)
        ])
        summary.value = summaryData
        weightTrend.value = trendData
      } catch (error) {
        console.error('Load stats error:', error)
        showError('加载失败')
      }
    }

    const goToProfile = () => {
      uni.navigateTo({ url: '/pages/profile/index' })
    }

    onMounted(() => {
      loadData()
    })

    return {
      summary,
      weightTrend,
      timeRanges,
      timeRangeIndex,
      avgCaloriesIn,
      avgCaloriesOut,
      weightChangeText,
      weightChangeColor,
      dietCompletionRate,
      workoutCompletionRate,
      getWeightPercent,
      onTimeRangeChange,
      loadData,
      goToProfile
    }
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  background-color: var(--bg-color);
  min-height: 100vh;
  padding-bottom: 40rpx;
}

.stats-overview {
  .overview-title {
    font-size: 30rpx;
    font-weight: bold;
    color: var(--text-primary);
    margin-bottom: 24rpx;
  }

  .overview-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16rpx;

    .stat-item {
      text-align: center;
      padding: 16rpx 8rpx;
      background-color: #FFF8E5;
      border-radius: 12rpx;

      .stat-value {
        font-size: 28rpx;
        font-weight: bold;
        color: var(--color-primary);
        display: block;
      }

      .stat-label {
        font-size: 20rpx;
        color: var(--text-hint);
        margin-top: 4rpx;
        display: block;
      }
    }
  }
}

.section-title {
  font-size: 30rpx;
  font-weight: bold;
  color: var(--text-primary);
  margin: 32rpx 16rpx 16rpx;
}

.chart-card {
  .chart-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24rpx;

    .chart-title {
      font-size: 28rpx;
      font-weight: 500;
      color: var(--text-primary);
    }

    .time-picker {
      font-size: 24rpx;
      color: var(--color-primary);
      padding: 8rpx 16rpx;
      background-color: #FFF8E5;
      border-radius: 12rpx;
    }
  }

  .chart-container {
    .chart-placeholder {
      height: 300rpx;
      position: relative;

      .chart-mock {
        position: relative;
        height: 240rpx;
        border-left: 2rpx solid var(--border-color);
        border-bottom: 2rpx solid var(--border-color);

        .chart-point {
          position: absolute;
          width: 16rpx;
          height: 16rpx;
          background-color: var(--color-primary);
          border-radius: 50%;
          transform: translate(-50%, 50%);
        }
      }

      .chart-axis {
        text-align: center;
        margin-top: 12rpx;

        .axis-label {
          font-size: 22rpx;
          color: var(--text-hint);
        }
      }
    }
  }

  .empty-chart {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60rpx 24rpx;

    .empty-text {
      font-size: 28rpx;
      color: var(--text-hint);
      margin-bottom: 24rpx;
    }

    .add-weight-btn {
      background: linear-gradient(135deg, #FF8A65, #FFAB91);
      color: #FFFFFF;
      border-radius: 48rpx;
      padding: 16rpx 48rpx;
      border: none;
    }
  }
}

.completion-card {
  .completion-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12rpx;

    .completion-label {
      font-size: 26rpx;
      color: var(--text-secondary);
    }

    .completion-info {
      display: flex;
      align-items: center;
      gap: 16rpx;

      .completion-value {
        font-size: 24rpx;
        color: var(--text-primary);
      }

      .completion-percent {
        font-size: 28rpx;
        font-weight: bold;
        color: var(--color-primary);
      }
    }
  }

  .progress-bar {
    width: 100%;
    height: 12rpx;
    background-color: #FFE0B2;
    border-radius: 6rpx;
    overflow: hidden;
    margin-bottom: 24rpx;

    .progress-fill {
      height: 100%;
      border-radius: 6rpx;
      transition: width 0.3s ease;

      &.diet {
        background: linear-gradient(90deg, #FF8A65, #FFCC80);
      }

      &.workout {
        background: linear-gradient(90deg, #81C784, #C8E6C9);
      }
    }
  }
}

.refresh-btn {
  position: fixed;
  bottom: 40rpx;
  left: 50%;
  transform: translateX(-50%);
  width: 80%;
  max-width: 600rpx;
  height: 88rpx;
  line-height: 88rpx;
  background: linear-gradient(135deg, #FF8A65, #FFAB91);
  color: #FFFFFF;
  font-size: 30rpx;
  font-weight: bold;
  border-radius: 44rpx;
  border: none;
  box-shadow: var(--shadow-float);

  &:active {
    opacity: 0.8;
  }
}
</style>
