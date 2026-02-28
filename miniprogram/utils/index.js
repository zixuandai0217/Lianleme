/**
 * 工具函数
 */

/**
 * 格式化日期
 */
export function formatDate(date, format = 'YYYY-MM-DD') {
  if (!date) return ''

  const d = new Date(date)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hours = String(d.getHours()).padStart(2, '0')
  const minutes = String(d.getMinutes()).padStart(2, '0')
  const seconds = String(d.getSeconds()).padStart(2, '0')

  return format
    .replace('YYYY', year)
    .replace('MM', month)
    .replace('DD', day)
    .replace('HH', hours)
    .replace('mm', minutes)
    .replace('ss', seconds)
}

/**
 * 格式化数字（添加千分位）
 */
export function formatNumber(num) {
  if (num === null || num === undefined) return '0'
  return Number(num).toLocaleString()
}

/**
 * 格式化体重
 */
export function formatWeight(weight) {
  if (weight === null || weight === undefined) return '--'
  return `${Number(weight).toFixed(1)}kg`
}

/**
 * 格式化卡路里
 */
export function formatCalories(calories) {
  if (calories === null || calories === undefined) return '--'
  return `${Math.round(calories)}kcal`
}

/**
 * 计算 BMI
 */
export function calculateBMI(weight, height) {
  if (!weight || !height) return 0
  const heightInMeters = height / 100
  return (weight / (heightInMeters * heightInMeters)).toFixed(1)
}

/**
 * 获取 BMI 分类
 */
export function getBMICategory(bmi) {
  if (bmi < 18.5) return { text: '偏瘦', color: '#FFB74D' }
  if (bmi < 24) return { text: '正常', color: '#81C784' }
  if (bmi < 28) return { text: '偏胖', color: '#FFB74D' }
  return { text: '肥胖', color: '#E57373' }
}

/**
 * 获取活动水平文本
 */
export function getActivityLevelText(level) {
  const map = {
    sedentary: '久坐少动',
    light: '轻度活动',
    moderate: '中度活动',
    active: '活跃',
    very_active: '非常活跃'
  }
  return map[level] || '中度活动'
}

/**
 * 获取目标类型文本
 */
export function getGoalTypeText(type) {
  const map = {
    lose_weight: '减重',
    gain_muscle: '增肌',
    maintain: '维持'
  }
  return map[type] || '减重'
}

/**
 * 防抖函数
 */
export function debounce(func, wait = 300) {
  let timeout
  return function (...args) {
    clearTimeout(timeout)
    timeout = setTimeout(() => func.apply(this, args), wait)
  }
}

/**
 * 节流函数
 */
export function throttle(func, limit = 500) {
  let inThrottle
  return function (...args) {
    if (!inThrottle) {
      func.apply(this, args)
      inThrottle = true
      setTimeout(() => inThrottle = false, limit)
    }
  }
}

/**
 * 深拷贝
 */
export function deepClone(obj) {
  if (obj === null || typeof obj !== 'object') return obj
  if (obj instanceof Date) return new Date(obj)
  if (obj instanceof Array) return obj.map(item => deepClone(item))

  const cloned = {}
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      cloned[key] = deepClone(obj[key])
    }
  }
  return cloned
}

/**
 * 显示成功提示
 */
export function showSuccess(message) {
  uni.showToast({
    title: message,
    icon: 'success',
    duration: 2000
  })
}

/**
 * 显示错误提示
 */
export function showError(message) {
  uni.showToast({
    title: message,
    icon: 'none',
    duration: 2000
  })
}
