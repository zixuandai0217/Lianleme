<template>
  <view class="page-container">
    <view class="form-container">
      <view class="form-title">身体数据录入</view>

      <!-- 基础数据 -->
      <view class="form-section">
        <view class="section-title">基础数据</view>

        <view class="form-item">
          <text class="form-label">身高 (cm)</text>
          <input
            v-model="formData.height"
            type="digit"
            placeholder="请输入身高"
            class="form-input"
          />
        </view>

        <view class="form-item">
          <text class="form-label">体重 (kg)</text>
          <input
            v-model="formData.weight"
            type="digit"
            placeholder="请输入体重"
            class="form-input"
          />
        </view>

        <view class="form-item">
          <text class="form-label">体脂率 (%)</text>
          <input
            v-model="formData.bodyFatRate"
            type="digit"
            placeholder="可选，如有体脂秤可填写"
            class="form-input"
          />
        </view>
      </view>

      <!-- 目标设置 -->
      <view class="form-section">
        <view class="section-title">目标设置</view>

        <view class="form-item">
          <text class="form-label">目标类型</text>
          <picker
            :range="goalTypes"
            range-key="label"
            :value="goalTypeIndex"
            @change="onGoalTypeChange"
          >
            <view class="picker-value">{{ goalTypes[goalTypeIndex].label }}</view>
          </picker>
        </view>

        <view class="form-item">
          <text class="form-label">目标体重 (kg)</text>
          <input
            v-model="formData.targetWeight"
            type="digit"
            placeholder="请输入目标体重"
            class="form-input"
          />
        </view>

        <view class="form-item">
          <text class="form-label">每周目标 (kg)</text>
          <picker
            :range="weeklyGoals"
            range-key="label"
            :value="weeklyGoalIndex"
            @change="onWeeklyGoalChange"
          >
            <view class="picker-value">{{ weeklyGoals[weeklyGoalIndex].label }}</view>
          </picker>
        </view>
      </view>

      <!-- 活动水平 -->
      <view class="form-section">
        <view class="section-title">活动水平</view>

        <view class="form-item">
          <text class="form-label">日常活动量</text>
          <picker
            :range="activityLevels"
            range-key="label"
            :value="activityLevelIndex"
            @change="onActivityLevelChange"
          >
            <view class="picker-value">{{ activityLevels[activityLevelIndex].label }}</view>
          </picker>
        </view>

        <view class="form-item">
          <text class="form-label">每周运动天数</text>
          <picker
            :range="exerciseDays"
            :value="exerciseDaysIndex"
            @change="onExerciseDaysChange"
          >
            <view class="picker-value">{{ exerciseDays[exerciseDaysIndex] }}天</view>
          </picker>
        </view>
      </view>

      <!-- 提交按钮 -->
      <button class="submit-btn" @click="handleSubmit">保存数据</button>
    </view>
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { profileApi } from '@/api'
import { showSuccess, showError } from '@/utils'

export default {
  name: 'ProfileEdit',
  setup() {
    const formData = ref({
      height: '',
      weight: '',
      bodyFatRate: '',
      targetWeight: '',
      weeklyGoal: 0.5
    })

    const goalTypes = [
      { value: 'lose_weight', label: '减重' },
      { value: 'gain_muscle', label: '增肌' },
      { value: 'maintain', label: '维持' }
    ]
    const goalTypeIndex = ref(0)

    const weeklyGoals = [
      { label: '0.25kg (温和)' },
      { label: '0.5kg (推荐)' },
      { label: '0.75kg (较快)' },
      { label: '1kg (快速)' }
    ]
    const weeklyGoalIndex = ref(1)

    const activityLevels = [
      { value: 'sedentary', label: '久坐少动 (几乎不运动)' },
      { value: 'light', label: '轻度活动 (每周 1-3 次)' },
      { value: 'moderate', label: '中度活动 (每周 3-5 次)' },
      { value: 'active', label: '活跃 (每周 6-7 次)' },
      { value: 'very_active', label: '非常活跃 (体力工作)' }
    ]
    const activityLevelIndex = ref(2)

    const exerciseDays = [0, 1, 2, 3, 4, 5, 6, 7]
    const exerciseDaysIndex = ref(3)

    const onGoalTypeChange = (e) => {
      goalTypeIndex.value = e.detail.value
    }

    const onWeeklyGoalChange = (e) => {
      weeklyGoalIndex.value = e.detail.value
      const values = [0.25, 0.5, 0.75, 1]
      formData.value.weeklyGoal = values[weeklyGoalIndex.value]
    }

    const onActivityLevelChange = (e) => {
      activityLevelIndex.value = e.detail.value
    }

    const onExerciseDaysChange = (e) => {
      exerciseDaysIndex.value = e.detail.value
    }

    const validateForm = () => {
      if (!formData.value.height || formData.value.height < 50 || formData.value.height > 250) {
        showError('请输入正确的身高值')
        return false
      }
      if (!formData.value.weight || formData.value.weight < 20 || formData.value.weight > 300) {
        showError('请输入正确的体重值')
        return false
      }
      if (formData.value.targetWeight && (formData.value.targetWeight < 20 || formData.value.targetWeight > 300)) {
        showError('请输入正确的目标体重')
        return false
      }
      return true
    }

    const handleSubmit = async () => {
      if (!validateForm()) return

      uni.showLoading({ title: '保存中...' })

      try {
        const data = {
          height: parseFloat(formData.value.height),
          weight: parseFloat(formData.value.weight),
          body_fat_rate: formData.value.bodyFatRate ? parseFloat(formData.value.bodyFatRate) : null,
          target_weight: formData.value.targetWeight ? parseFloat(formData.value.targetWeight) : null,
          weekly_goal: formData.value.weeklyGoal,
          goal_type: goalTypes[goalTypeIndex.value].value,
          activity_level: activityLevels[activityLevelIndex.value].value,
          exercise_days_per_week: exerciseDays[exerciseDaysIndex.value]
        }

        await profileApi.create(data)
        uni.hideLoading()
        showSuccess('保存成功')

        setTimeout(() => {
          uni.navigateBack()
        }, 500)
      } catch (error) {
        uni.hideLoading()
        showError(error.message || '保存失败')
      }
    }

    return {
      formData,
      goalTypes,
      goalTypeIndex,
      weeklyGoals,
      weeklyGoalIndex,
      activityLevels,
      activityLevelIndex,
      exerciseDays,
      exerciseDaysIndex,
      onGoalTypeChange,
      onWeeklyGoalChange,
      onActivityLevelChange,
      onExerciseDaysChange,
      handleSubmit
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

.form-container {
  padding: 20rpx;
}

.form-title {
  font-size: 36rpx;
  font-weight: bold;
  color: var(--text-primary);
  text-align: center;
  padding: 32rpx 0;
}

.form-section {
  background-color: #FFFFFF;
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;

  .section-title {
    font-size: 28rpx;
    font-weight: bold;
    color: var(--color-primary);
    margin-bottom: 20rpx;
    padding-bottom: 12rpx;
    border-bottom: 1rpx solid var(--border-color);
  }
}

.form-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20rpx 0;
  border-bottom: 1rpx solid #F5F5F5;

  &:last-child {
    border-bottom: none;
  }

  .form-label {
    font-size: 28rpx;
    color: var(--text-primary);
  }

  .form-input,
  .picker-value {
    width: 300rpx;
    text-align: right;
    font-size: 28rpx;
    color: var(--text-primary);
  }
}

.submit-btn {
  width: 100%;
  height: 96rpx;
  line-height: 96rpx;
  background: linear-gradient(135deg, #FF8A65, #FFAB91);
  color: #FFFFFF;
  font-size: 32rpx;
  font-weight: bold;
  border-radius: 48rpx;
  border: none;
  margin-top: 32rpx;
  margin-bottom: env(safe-area-inset-bottom);

  &:active {
    opacity: 0.8;
  }
}
</style>
