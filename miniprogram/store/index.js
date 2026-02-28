/**
 * 全局状态管理 - Pinia
 */
import { defineStore } from 'pinia'

/**
 * 用户状态
 */
export const useUserStore = defineStore('user', {
  state: () => ({
    token: '',
    userInfo: null,
    userProfile: null
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    nickname: (state) => state.userInfo?.nickname || '用户',
    avatar: (state) => state.userInfo?.avatar_url || '/static/default-avatar.png'
  },

  actions: {
    // 设置 Token
    setToken(token) {
      this.token = token
      uni.setStorageSync('token', token)
    },

    // 设置用户信息
    setUserInfo(info) {
      this.userInfo = info
    },

    // 设置用户资料
    setUserProfile(profile) {
      this.userProfile = profile
    },

    // 退出登录
    logout() {
      this.token = ''
      this.userInfo = null
      this.userProfile = null
      uni.removeStorageSync('token')
    },

    // 从本地恢复登录状态
    restoreAuth() {
      const token = uni.getStorageSync('token')
      if (token) {
        this.token = token
      }
    }
  }
})

/**
 * 身体数据状态
 */
export const useProfileStore = defineStore('profile', {
  state: () => ({
    currentProfile: null,
    profiles: []
  }),

  getters: {
    bmi: (state) => state.currentProfile?.bmi,
    goalType: (state) => state.currentProfile?.goal_type || 'lose_weight',
    targetWeight: (state) => state.currentProfile?.target_weight
  },

  actions: {
    setCurrentProfile(profile) {
      this.currentProfile = profile
    },

    setProfiles(profiles) {
      this.profiles = profiles
    }
  }
})

/**
 * 饮食状态
 */
export const useDietStore = defineStore('diet', {
  state: () => ({
    todayPlan: null,
    todayLogs: []
  }),

  getters: {
    todayCalories: (state) => {
      return state.todayLogs.reduce((sum, log) => sum + (log.total_calories || 0), 0)
    },
    todayProgress: (state) => {
      if (!state.todayPlan || !state.todayPlan.daily_calories) return 0
      return Math.round((this.todayCalories / state.todayPlan.daily_calories) * 100)
    }
  },

  actions: {
    setTodayPlan(plan) {
      this.todayPlan = plan
    },

    setTodayLogs(logs) {
      this.todayLogs = logs
    }
  }
})

/**
 * 运动状态
 */
export const useWorkoutStore = defineStore('workout', {
  state: () => ({
    currentPlan: null,
    todayWorkout: null
  }),

  getters: {
    todayCaloriesBurn: (state) => state.todayWorkout?.calories_burned || 0,
    workoutCompleted: (state) => state.todayWorkout?.status === 'completed'
  },

  actions: {
    setCurrentPlan(plan) {
      this.currentPlan = plan
    },

    setTodayWorkout(workout) {
      this.todayWorkout = workout
    }
  }
})
