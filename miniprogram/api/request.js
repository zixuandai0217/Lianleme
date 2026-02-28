/**
 * API 请求封装
 */
import { getSettings } from './settings'

const settings = getSettings()

/**
 * 发起 HTTP 请求
 */
async function request(options) {
  const {
    url,
    method = 'GET',
    data,
    needAuth = true,
    showLoading = true
  } = options

  // 显示加载提示
  if (showLoading) {
    uni.showLoading({
      title: '加载中...',
      mask: true
    })
  }

  try {
    // 获取 token
    const token = getToken()

    // 构建完整 URL
    const fullUrl = `${settings.API_BASE_URL}${url}`

    // 设置请求头
    const header = {
      'Content-Type': 'application/json',
      ...(token && needAuth ? { 'Authorization': `Bearer ${token}` } : {})
    }

    // 发起请求
    const response = await uni.request({
      url: fullUrl,
      method,
      header,
      data
    })

    const [error, res] = response

    if (error) {
      throw new Error('网络请求失败')
    }

    // 隐藏加载提示
    if (showLoading) {
      uni.hideLoading()
    }

    // 检查状态码
    const statusCode = res.statusCode

    // Token 过期处理
    if (statusCode === 401) {
      handleTokenExpired()
      throw new Error('请先登录')
    }

    // 返回数据
    const responseData = res.data

    // 如果是统一响应格式
    if (responseData && responseData.success !== undefined) {
      if (responseData.success) {
        return responseData.data
      } else {
        const errorMsg = responseData.error?.message || responseData.message || '操作失败'
        uni.showToast({
          title: errorMsg,
          icon: 'none'
        })
        throw new Error(errorMsg)
      }
    }

    return responseData

  } catch (error) {
    console.error('Request error:', error)

    if (showLoading) {
      uni.hideLoading()
    }

    // 非业务错误提示
    if (error.message && !error.message.includes('请先登录')) {
      uni.showToast({
        title: error.message,
        icon: 'none',
        duration: 2000
      })
    }

    throw error
  }
}

/**
 * GET 请求
 */
function get(url, data, options = {}) {
  return request({ url, method: 'GET', data, ...options })
}

/**
 * POST 请求
 */
function post(url, data, options = {}) {
  return request({ url, method: 'POST', data, ...options })
}

/**
 * PUT 请求
 */
function put(url, data, options = {}) {
  return request({ url, method: 'PUT', data, ...options })
}

/**
 * DELETE 请求
 */
function del(url, data, options = {}) {
  return request({ url, method: 'DELETE', data, ...options })
}

/**
 * 获取本地存储的 Token
 */
function getToken() {
  try {
    return uni.getStorageSync('token') || ''
  } catch (e) {
    return ''
  }
}

/**
 * 保存 Token
 */
function saveToken(token) {
  try {
    uni.setStorageSync('token', token)
  } catch (e) {
    console.error('Save token error:', e)
  }
}

/**
 * 清除 Token
 */
function clearToken() {
  try {
    uni.removeStorageSync('token')
  } catch (e) {
    console.error('Clear token error:', e)
  }
}

/**
 * 处理 Token 过期
 */
function handleTokenExpired() {
  clearToken()
  // 跳转到登录页
  uni.reLaunch({
    url: '/pages/login/index'
  })
}

/**
 * 检查是否已登录
 */
function isLogin() {
  return !!getToken()
}

export default {
  request,
  get,
  post,
  put,
  delete: del,
  getToken,
  saveToken,
  clearToken,
  isLogin
}
