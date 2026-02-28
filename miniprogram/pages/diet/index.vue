<template>
  <view class="page-container">
    <!-- 饮食计划 -->
    <view class="plan-card card" v-if="todayPlan">
      <view class="plan-header">
        <view>
          <text class="plan-title">今日饮食计划</text>
          <text class="plan-subtitle">总热量 {{ todayPlan.daily_calories }}kcal</text>
        </view>
        <view class="plan-progress">
          <text class="progress-text">{{ todayProgress }}%</text>
        </view>
      </view>

      <view class="nutrition-bar">
        <view class="nutrient protein">
          <text class="nutrient-value">{{ todayPlan.protein }}g</text>
          <text class="nutrient-label">蛋白质</text>
        </view>
        <view class="nutrient carbs">
          <text class="nutrient-value">{{ todayPlan.carbohydrates }}g</text>
          <text class="nutrient-label">碳水</text>
        </view>
        <view class="nutrient fat">
          <text class="nutrient-value">{{ todayPlan.fat }}g</text>
          <text class="nutrient-label">脂肪</text>
        </view>
      </view>

      <view class="water-reminder">
        <text class="water-icon">💧</text>
        <text class="water-text">建议饮水 {{ todayPlan.water }}ml</text>
      </view>
    </view>

    <!-- 餐次详情 -->
    <view class="section-title" v-if="todayPlan">餐次详情</view>
    <view class="meals-list" v-if="todayPlan?.meals">
      <view class="meal-item card" v-for="(meal, key) in todayPlan.meals" :key="key">
        <view class="meal-header">
          <text class="meal-icon">{{ getMealIcon(key) }}</text>
          <view class="meal-info">
            <text class="meal-name">{{ getMealName(key) }}</text>
            <text class="meal-calories">{{ meal.calories }}kcal</text>
          </view>
        </view>

        <view class="meal-foods">
          <view class="food-item" v-for="(food, index) in meal.foods" :key="index">
            <text class="food-name">{{ food.name }}</text>
            <text class="food-grams">{{ food.grams }}g</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 无计划提示 -->
    <view class="empty-state" v-if="!todayPlan">
      <view class="empty-icon">🍽️</view>
      <text class="empty-text">暂无今日饮食计划</text>
      <button class="generate-btn" @click="generatePlan">AI 生成计划</button>
    </view>

    <!-- 记录按钮 -->
    <view class="record-btn-wrapper" v-if="todayPlan">
      <button class="record-btn" @click="goToLog">
        <text class="record-btn-icon">📝</text>
        <text class="record-btn-text">记录饮食</text>
      </button>
    </view>
  </view>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { dietApi } from '@/api'
import { useDietStore } from '@/store'
import { showSuccess, showError } from '@/utils'

export default {
  name: 'DietIndex',
  setup() {
    const dietStore = useDietStore()
    const todayPlan = ref(null)
    const todayProgress = ref(0)

    const getMealName = (key) => {
      const map = {
        breakfast: '早餐',
        lunch: '午餐',
        dinner: '晚餐',
        snacks: '加餐'
      }
      return map[key] || key
    }

    const getMealIcon = (key) => {
      const map = {
        breakfast: '🌅',
        lunch: '☀️',
        dinner: '🌙',
        snacks: '🍎'
      }
      return map[key] || '🍽️'
    }

    const generatePlan = async () => {
      uni.showLoading({ title: 'AI 生成中...' })
      try {
        const plan = await dietApi.generate()
        todayPlan.value = plan
        dietStore.setTodayPlan(plan)
        uni.hideLoading()
        showSuccess('饮食计划已生成')
      } catch (error) {
        uni.hideLoading()
        showError(error.message || '生成失败，请先录入身体数据')
      }
    }

    const goToLog = () => {
      uni.navigateTo({ url: '/pages/diet/log' })
    }

    onMounted(async () => {
      try {
        const plan = await dietApi.getToday()
        todayPlan.value = plan
        dietStore.setTodayPlan(plan)
      } catch (e) {
        console.log('暂无今日计划')
      }
    })

    return {
      todayPlan,
      todayProgress,
      getMealName,
      getMealIcon,
      generatePlan,
      goToLog
    }
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20rpx;
  padding-bottom: 160rpx;
}

.plan-card {
  .plan-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24rpx;

    .plan-title {
      font-size: 30rpx;
      font-weight: bold;
      display: block;
    }

    .plan-subtitle {
      font-size: 24rpx;
      color: var(--text-hint);
    }

    .plan-progress {
      background: linear-gradient(135deg, #FF8A65, #FFCC80);
      border-radius: 50%;
      width: 80rpx;
      height: 80rpx;
      display: flex;
      align-items: center;
      justify-content: center;

      .progress-text {
        font-size: 24rpx;
        font-weight: bold;
        color: #FFFFFF;
      }
    }
  }

  .nutrition-bar {
    display: flex;
    justify-content: space-around;
    padding: 24rpx 0;
    border-top: 1rpx solid var(--border-color);
    border-bottom: 1rpx solid var(--border-color);

    .nutrient {
      text-align: center;

      .nutrient-value {
        font-size: 32rpx;
        font-weight: bold;
        display: block;
      }

      .nutrient-label {
        font-size: 22rpx;
        color: var(--text-hint);
      }
    }

    .protein .nutrient-value { color: #E57373; }
    .carbs .nutrient-value { color: #FFB74D; }
    .fat .nutrient-value { color: #81C784; }
  }

  .water-reminder {
    display: flex;
    align-items: center;
    margin-top: 16rpx;
    padding: 16rpx;
    background-color: #E3F2FD;
    border-radius: 12rpx;

    .water-icon {
      font-size: 32rpx;
      margin-right: 12rpx;
    }

    .water-text {
      font-size: 26rpx;
      color: #1976D2;
    }
  }
}

.section-title {
  font-size: 30rpx;
  font-weight: bold;
  margin: 32rpx 16rpx 16rpx;
}

.meals-list {
  .meal-item {
    margin: 16rpx;

    .meal-header {
      display: flex;
      align-items: center;
      margin-bottom: 16rpx;

      .meal-icon {
        font-size: 36rpx;
        margin-right: 16rpx;
      }

      .meal-info {
        flex: 1;
        display: flex;
        justify-content: space-between;
        align-items: center;

        .meal-name {
          font-size: 28rpx;
          font-weight: 500;
          color: var(--text-primary);
        }

        .meal-calories {
          font-size: 24rpx;
          color: var(--color-primary);
          font-weight: 500;
        }
      }
    }

    .meal-foods {
      background-color: #FFF8E5;
      border-radius: 12rpx;
      padding: 16rpx;

      .food-item {
        display: flex;
        justify-content: space-between;
        padding: 8rpx 0;
        font-size: 26rpx;

        .food-name {
          color: var(--text-secondary);
        }

        .food-grams {
          color: var(--text-hint);
        }
      }
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

.record-btn-wrapper {
  position: fixed;
  bottom: 20rpx;
  left: 0;
  right: 0;
  padding: 0 20rpx;

  .record-btn {
    width: 100%;
    height: 96rpx;
    background: linear-gradient(135deg, #FF8A65, #FFAB91);
    border-radius: 48rpx;
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow-float);

    .record-btn-icon {
      font-size: 36rpx;
      margin-right: 12rpx;
    }

    .record-btn-text {
      font-size: 30rpx;
      color: #FFFFFF;
      font-weight: 500;
    }
  }
}
</style>
