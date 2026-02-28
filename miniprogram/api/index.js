/**
 * API 接口定义
 */
import http from './request'

/**
 * 认证相关接口
 */
export const authApi = {
  // 获取验证码
  getVerifyCode(phone) {
    return http.post('/auth/verify-code', { phone })
  },

  // 登录/注册
  login(phone, code) {
    return http.post('/auth/login', { phone, verify_code: code })
  },

  // 登出
  logout() {
    return http.post('/auth/logout')
  },

  // 获取当前用户信息
  getMe() {
    return http.get('/auth/me')
  }
}

/**
 * 用户接口
 */
export const userApi = {
  // 获取用户资料
  getProfile() {
    return http.get('/users/profile')
  },

  // 更新用户资料
  updateProfile(data) {
    return http.put('/users/profile', data)
  }
}

/**
 * 身体数据接口
 */
export const profileApi = {
  // 获取最新身体数据
  getCurrent() {
    return http.get('/profiles/current')
  },

  // 获取历史记录
  getHistory(limit = 30) {
    return http.get('/profiles/history', { limit })
  },

  // 创建身体数据
  create(data) {
    return http.post('/profiles', data)
  },

  // 更新身体数据
  update(id, data) {
    return http.put(`/profiles/${id}`, data)
  },

  // 删除身体数据
  delete(id) {
    return http.delete(`/profiles/${id}`)
  }
}

/**
 * 饮食计划接口
 */
export const dietApi = {
  // 获取今日饮食
  getToday() {
    return http.get('/diet/today')
  },

  // 生成饮食计划
  generate(days = 7) {
    return http.post('/diet/generate', { days })
  },

  // 获取计划列表
  getPlans(limit = 7) {
    return http.get('/diet/plans', { limit })
  },

  // 获取饮食记录
  getLogs(startDate, endDate) {
    return http.get('/diet/logs', { start_date: startDate, end_date: endDate })
  },

  // 创建饮食记录
  createLog(data) {
    return http.post('/diet/logs', data)
  }
}

/**
 * 运动计划接口
 */
export const workoutApi = {
  // 获取当前运动计划
  getCurrent() {
    return http.get('/workout/current')
  },

  // 生成运动计划
  generate(weeks = 4, daysPerWeek = 5) {
    return http.post('/workout/generate', { weeks, days_per_week: daysPerWeek })
  },

  // 获取计划列表
  getPlans(limit = 5) {
    return http.get('/workout/plans', { limit })
  },

  // 获取运动记录
  getLogs(startDate, endDate) {
    return http.get('/workout/logs', { start_date: startDate, end_date: endDate })
  },

  // 创建运动记录
  createLog(data) {
    return http.post('/workout/logs', data)
  },

  // 更新运动记录
  updateLog(id, data) {
    return http.put(`/workout/logs/${id}`, data)
  }
}

/**
 * 统计数据接口
 */
export const statsApi = {
  // 获取每日统计
  getDaily(startDate, endDate) {
    return http.get('/stats/daily', { start_date: startDate, end_date: endDate })
  },

  // 获取汇总统计
  getSummary(days = 7) {
    return http.get('/stats/summary', { days })
  },

  // 获取体重趋势
  getTrend(days = 30) {
    return http.get('/stats/trend', { days })
  },

  // 更新统计
  update(date) {
    return http.post('/stats/update', { stat_date: date })
  }
}

/**
 * AI 聊天接口
 */
export const chatApi = {
  // 发送消息
  send(sessionId, message) {
    return http.post('/ai/chat', { session_id: sessionId, message })
  },

  // 获取会话列表
  getSessions() {
    return http.get('/ai/sessions')
  },

  // 获取会话消息
  getSessionMessages(sessionId) {
    return http.get(`/ai/sessions/${sessionId}`)
  },

  // 删除会话
  deleteSession(sessionId) {
    return http.delete(`/ai/sessions/${sessionId}`)
  }
}
