/**
 * 应用配置
 */
export function getSettings() {
  // 开发环境
  if (process.env.NODE_ENV === 'development') {
    return {
      API_BASE_URL: 'http://localhost:8000/api/v1',
      DEBUG: true
    }
  }

  // 生产环境（小程序）
  #ifdef MP-WEIXIN
    return {
      API_BASE_URL: 'https://your-domain.com/api/v1',
      DEBUG: false
    }
  #endif

  // H5 生产环境
  return {
    API_BASE_URL: 'https://your-domain.com/api/v1',
    DEBUG: false
  }
}
