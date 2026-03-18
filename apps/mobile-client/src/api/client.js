const BASE_URL = 'http://localhost:8000/v1'

export const apiGet = (path) => {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}${path}`,
      method: 'GET',
      success: (res) => resolve(res.data),
      fail: reject,
    })
  })
}

export const apiPost = (path, data) => {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}${path}`,
      method: 'POST',
      data,
      success: (res) => resolve(res.data),
      fail: reject,
    })
  })
}
