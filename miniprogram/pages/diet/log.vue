<template>
  <view class="page-container">
    <view class="log-container">
      <view class="log-title">饮食记录</view>

      <!-- 选择餐次 -->
      <view class="meal-selector card">
        <view
          class="meal-item"
          v-for="meal in mealTypes"
          :key="meal.value"
          :class="{ active: selectedMeal === meal.value }"
          @click="selectedMeal = meal.value"
        >
          <text class="meal-icon">{{ meal.icon }}</text>
          <text class="meal-name">{{ meal.label }}</text>
        </view>
      </view>

      <!-- 食物列表 -->
      <view class="food-list card">
        <view class="list-header">
          <text class="list-title">添加食物</text>
        </view>

        <view class="food-items">
          <view class="food-item" v-for="(food, index) in foods" :key="index">
            <view class="food-info">
              <input
                v-model="food.name"
                placeholder="食物名称"
                class="food-input name-input"
              />
              <view class="food-meta">
                <input
                  v-model="food.grams"
                  type="digit"
                  placeholder="克数"
                  class="food-input small-input"
                />
                <text class="input-label">g</text>
              </view>
            </view>
            <view class="food-actions">
              <text class="food-calories">{{ calculateFoodCalories(food) }}kcal</text>
              <text class="delete-btn" @click="removeFood(index)">×</text>
            </view>
          </view>
        </view>

        <view class="add-food-btn" @click="addFood">
          <text class="add-icon">+</text>
          <text class="add-text">添加食物</text>
        </view>
      </view>

      <!-- 营养总计 -->
      <view class="summary-card card">
        <view class="summary-title">总计</view>
        <view class="summary-grid">
          <view class="summary-item">
            <text class="summary-value highlight">{{ totalCalories }}</text>
            <text class="summary-label">卡路里</text>
          </view>
          <view class="summary-item">
            <text class="summary-value">{{ totalProtein }}g</text>
            <text class="summary-label">蛋白质</text>
          </view>
          <view class="summary-item">
            <text class="summary-value">{{ totalCarbs }}g</text>
            <text class="summary-label">碳水</text>
          </view>
          <view class="summary-item">
            <text class="summary-value">{{ totalFat }}g</text>
            <text class="summary-label">脂肪</text>
          </view>
        </view>
      </view>

      <!-- 备注 -->
      <view class="notes-section card">
        <textarea
          v-model="notes"
          placeholder="备注（可选）"
          class="notes-input"
          maxlength="200"
        />
      </view>

      <!-- 提交按钮 -->
      <button class="submit-btn" @click="handleSubmit">保存记录</button>
    </view>
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { dietApi } from '@/api'
import { showSuccess, showError } from '@/utils'

export default {
  name: 'DietLog',
  setup() {
    const selectedMeal = ref('breakfast')
    const foods = ref([
      { name: '', grams: '', calories: 0, protein: 0, carbs: 0, fat: 0 }
    ])
    const notes = ref('')

    const mealTypes = [
      { value: 'breakfast', label: '早餐', icon: '🌅' },
      { value: 'lunch', label: '午餐', icon: '☀️' },
      { value: 'dinner', label: '晚餐', icon: '🌙' },
      { value: 'snack', label: '加餐', icon: '🍎' }
    ]

    const calculateFoodCalories = (food) => {
      // 简单估算：100g 食物平均约 150kcal
      if (!food.grams) return 0
      return Math.round(parseFloat(food.grams) * 1.5)
    }

    const totalCalories = computed(() => {
      return foods.value.reduce((sum, food) => sum + calculateFoodCalories(food), 0)
    })

    const totalProtein = computed(() => 0) // 简化版本
    const totalCarbs = computed(() => 0)
    const totalFat = computed(() => 0)

    const addFood = () => {
      foods.value.push({ name: '', grams: '', calories: 0, protein: 0, carbs: 0, fat: 0 })
    }

    const removeFood = (index) => {
      if (foods.value.length === 1) {
        showError('至少保留一个食物')
        return
      }
      foods.value.splice(index, 1)
    }

    const validateForm = () => {
      const hasFood = foods.value.some(f => f.name.trim())
      if (!hasFood) {
        showError('请至少添加一个食物')
        return false
      }
      return true
    }

    const handleSubmit = async () => {
      if (!validateForm()) return

      uni.showLoading({ title: '保存中...' })

      try {
        const today = new Date().toISOString().split('T')[0]

        const foodData = foods.value
          .filter(f => f.name.trim())
          .map(f => ({
            name: f.name,
            grams: parseFloat(f.grams) || 100,
            calories: calculateFoodCalories(f)
          }))

        await dietApi.createLog({
          log_date: today,
          meal_type: selectedMeal.value,
          foods: foodData,
          notes: notes.value
        })

        uni.hideLoading()
        showSuccess('记录已保存')

        setTimeout(() => {
          uni.navigateBack()
        }, 500)
      } catch (error) {
        uni.hideLoading()
        showError(error.message || '保存失败')
      }
    }

    return {
      mealTypes,
      selectedMeal,
      foods,
      notes,
      calculateFoodCalories,
      totalCalories,
      totalProtein,
      totalCarbs,
      totalFat,
      addFood,
      removeFood,
      handleSubmit
    }
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  background-color: var(--bg-color);
  min-height: 100vh;
  padding-bottom: 160rpx;
}

.log-container {
  padding: 20rpx;
}

.log-title {
  font-size: 36rpx;
  font-weight: bold;
  color: var(--text-primary);
  text-align: center;
  padding: 24rpx 0;
}

.meal-selector {
  display: flex;
  justify-content: space-around;
  padding: 20rpx;

  .meal-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 16rpx 24rpx;
    border-radius: 16rpx;
    transition: all 0.3s ease;

    &.active {
      background-color: #FFF8E5;
    }

    .meal-icon {
      font-size: 36rpx;
      margin-bottom: 8rpx;
    }

    .meal-name {
      font-size: 24rpx;
      color: var(--text-primary);
    }
  }
}

.food-list {
  .list-header {
    .list-title {
      font-size: 28rpx;
      font-weight: bold;
      color: var(--text-primary);
    }
  }

  .food-items {
    .food-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16rpx 0;
      border-bottom: 1rpx solid #F5F5F5;

      .food-info {
        flex: 1;
        display: flex;
        align-items: center;

        .food-input {
          padding: 12rpx;
          background-color: #F5F5F5;
          border-radius: 8rpx;
          font-size: 26rpx;
        }

        .name-input {
          flex: 1;
          margin-right: 12rpx;
        }

        .small-input {
          width: 100rpx;
          text-align: center;
        }

        .food-meta {
          display: flex;
          align-items: center;

          .input-label {
            font-size: 24rpx;
            color: var(--text-hint);
            margin-left: 8rpx;
          }
        }
      }

      .food-actions {
        display: flex;
        align-items: center;

        .food-calories {
          font-size: 24rpx;
          color: var(--color-primary);
          font-weight: 500;
          margin-right: 16rpx;
        }

        .delete-btn {
          font-size: 40rpx;
          color: #E57373;
          padding: 0 8rpx;
        }
      }
    }
  }

  .add-food-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24rpx;
    background-color: #FFF8E5;
    border-radius: 12rpx;
    margin-top: 16rpx;

    .add-icon {
      font-size: 32rpx;
      color: var(--color-primary);
      margin-right: 8rpx;
    }

    .add-text {
      font-size: 26rpx;
      color: var(--color-primary);
    }
  }
}

.summary-card {
  .summary-title {
    font-size: 28rpx;
    font-weight: bold;
    color: var(--text-primary);
    margin-bottom: 16rpx;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16rpx;

    .summary-item {
      text-align: center;
      padding: 16rpx 8rpx;
      background-color: #FFF8E5;
      border-radius: 12rpx;

      .summary-value {
        font-size: 28rpx;
        font-weight: bold;
        color: var(--text-primary);
        display: block;

        &.highlight {
          color: var(--color-primary);
          font-size: 32rpx;
        }
      }

      .summary-label {
        font-size: 22rpx;
        color: var(--text-hint);
        margin-top: 4rpx;
        display: block;
      }
    }
  }
}

.notes-section {
  .notes-input {
    width: 100%;
    min-height: 160rpx;
    padding: 16rpx;
    background-color: #F5F5F5;
    border-radius: 12rpx;
    font-size: 26rpx;
    box-sizing: border-box;
  }
}

.submit-btn {
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
</style>
