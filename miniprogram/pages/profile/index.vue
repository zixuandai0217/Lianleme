<template>
  <view class="page-container">
    <!-- 身体数据卡片 -->
    <view class="profile-card card" v-if="currentProfile">
      <view class="card-header">
        <text class="card-title">最新数据</text>
        <text class="card-time">{{ formatDate(currentProfile.recorded_at) }}</text>
      </view>

      <view class="data-grid">
        <view class="data-item">
          <text class="data-label">体重</text>
          <text class="data-value">{{ currentProfile.weight }}</text>
          <text class="data-unit">kg</text>
        </view>
        <view class="data-item">
          <text class="data-label">BMI</text>
          <text class="data-value" :style="{ color: bmiColor }">{{ currentProfile.bmi }}</text>
        </view>
        <view class="data-item">
          <text class="data-label">目标体重</text>
          <text class="data-value">{{ currentProfile.target_weight || '--' }}</text>
          <text class="data-unit">kg</text>
        </view>
        <view class="data-item">
          <text class="data-label">目标类型</text>
          <text class="data-value-small">{{ goalTypeText }}</text>
        </view>
      </view>

      <view class="data-row" v-if="currentProfile.body_fat_rate">
        <text class="row-label">体脂率</text>
        <text class="row-value">{{ currentProfile.body_fat_rate }}%</text>
      </view>

      <view class="data-row" v-if="currentProfile.activity_level">
        <text class="row-label">活动水平</text>
        <text class="row-value">{{ activityLevelText }}</text>
      </view>
    </view>

    <!-- 无数据提示 -->
    <view class="empty-state" v-else>
      <view class="empty-icon">📝</view>
      <text class="empty-text">暂无身体数据</text>
      <button class="add-btn" @click="goToEdit">录入数据</button>
    </view>

    <!-- 历史记录 -->
    <view class="section-title" v-if="history.length > 0">历史记录</view>
    <view class="history-list" v-if="history.length > 0">
      <view class="history-item card" v-for="item in history" :key="item.id">
        <view class="history-date">{{ formatDate(item.recorded_at) }}</view>
        <view class="history-data">
          <text class="history-weight">{{ item.weight }}kg</text>
          <text class="history-bmi" v-if="item.bmi">BMI {{ item.bmi }}</text>
        </view>
      </view>
    </view>

    <!-- 悬浮按钮 -->
    <view class="fab" @click="goToEdit">
      <text class="fab-icon">+</text>
    </view>
  </view>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { profileApi } from '@/api'
import { formatDate, getBMICategory, getActivityLevelText, getGoalTypeText, showError } from '@/utils'

export default {
  name: 'ProfileIndex',
  setup() {
    const currentProfile = ref(null)
    const history = ref([])

    const bmiColor = computed(() => {
      if (!currentProfile.value?.bmi) return 'var(--text-primary)'
      const category = getBMICategory(currentProfile.value.bmi)
      return category.color
    })

    const goalTypeText = computed(() => {
      return getGoalTypeText(currentProfile.value?.goal_type)
    })

    const activityLevelText = computed(() => {
      return getActivityLevelText(currentProfile.value?.activity_level)
    })

    const loadData = async () => {
      try {
        const current = await profileApi.getCurrent()
        currentProfile.value = current

        const historyData = await profileApi.getHistory(10)
        history.value = historyData
      } catch (error) {
        console.error('Load profile error:', error)
      }
    }

    const goToEdit = () => {
      uni.navigateTo({ url: '/pages/profile/edit' })
    }

    onMounted(() => {
      loadData()
    })

    return {
      currentProfile,
      history,
      bmiColor,
      goalTypeText,
      activityLevelText,
      formatDate,
      goToEdit
    }
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20rpx;
  padding-bottom: 140rpx;
}

.profile-card {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24rpx;

    .card-title {
      font-size: 30rpx;
      font-weight: bold;
      color: var(--text-primary);
    }

    .card-time {
      font-size: 24rpx;
      color: var(--text-hint);
    }
  }

  .data-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24rpx;
    margin-bottom: 24rpx;

    .data-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 24rpx;
      background-color: #FFF8E5;
      border-radius: 16rpx;

      .data-label {
        font-size: 24rpx;
        color: var(--text-secondary);
        margin-bottom: 8rpx;
      }

      .data-value {
        font-size: 44rpx;
        font-weight: bold;
        color: var(--color-primary);
      }

      .data-unit {
        font-size: 20rpx;
        color: var(--text-hint);
      }

      .data-value-small {
        font-size: 28rpx;
        color: var(--text-primary);
      }
    }
  }

  .data-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16rpx 0;
    border-top: 1rpx solid var(--border-color);

    .row-label {
      font-size: 28rpx;
      color: var(--text-secondary);
    }

    .row-value {
      font-size: 28rpx;
      color: var(--text-primary);
      font-weight: 500;
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

  .add-btn {
    background: linear-gradient(135deg, #FF8A65, #FFAB91);
    color: #FFFFFF;
    border-radius: 48rpx;
    padding: 16rpx 48rpx;
    border: none;
  }
}

.section-title {
  font-size: 30rpx;
  font-weight: bold;
  color: var(--text-primary);
  margin: 32rpx 16rpx 16rpx;
}

.history-list {
  .history-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 24rpx;
    margin: 16rpx;

    .history-date {
      font-size: 26rpx;
      color: var(--text-hint);
    }

    .history-data {
      display: flex;
      align-items: center;
      gap: 24rpx;

      .history-weight {
        font-size: 32rpx;
        font-weight: bold;
        color: var(--color-primary);
      }

      .history-bmi {
        font-size: 24rpx;
        color: var(--text-secondary);
      }
    }
  }
}

.fab {
  position: fixed;
  right: 32rpx;
  bottom: 140rpx;
  width: 100rpx;
  height: 100rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #FF8A65, #FFAB91);
  box-shadow: var(--shadow-float);
  display: flex;
  align-items: center;
  justify-content: center;

  .fab-icon {
    font-size: 48rpx;
    color: #FFFFFF;
    font-weight: 300;
  }

  &:active {
    opacity: 0.8;
  }
}
</style>
