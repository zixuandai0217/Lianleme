// 封装 wx.request，统一鉴权 Header 与错误处理
// 从 app.js globalData 读取，统一在一处维护后端地址
const BASE_URL = () => getApp().globalData.baseUrl;

/**
 * 通用请求封装，自动附加 Authorization Header
 * @param {string} method HTTP 方法
 * @param {string} path 接口路径
 * @param {object} data 请求体
 */
function request(method, path, data = {}) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('auth_token');
    wx.request({
      url: `${BASE_URL()}${path}`,
      method,
      data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : ''
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else if (res.statusCode === 401) {
          wx.removeStorageSync('auth_token');
          wx.reLaunch({ url: '/pages/index/index' });
          reject(new Error('未授权，请重新登录'));
        } else {
          const msg = res.data?.detail || res.data?.message || `请求失败 ${res.statusCode}`;
          wx.showToast({ title: msg, icon: 'none' });
          reject(new Error(msg));
        }
      },
      fail(err) {
        wx.showToast({ title: '网络异常，请稍后重试', icon: 'none' });
        reject(err);
      }
    });
  });
}

/** 上传文件（multipart/form-data） */
function uploadFile(path, filePath, formData = {}) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('auth_token');
    wx.uploadFile({
      url: `${BASE_URL()}${path}`,
      filePath,
      name: 'file',
      formData,
      header: { 'Authorization': token ? `Bearer ${token}` : '' },
      success(res) {
        try {
          const data = JSON.parse(res.data);
          resolve(data);
        } catch {
          resolve(res.data);
        }
      },
      fail(err) {
        wx.showToast({ title: '上传失败', icon: 'none' });
        reject(err);
      }
    });
  });
}

module.exports = {
  get: (path) => request('GET', path),
  post: (path, data) => request('POST', path, data),
  put: (path, data) => request('PUT', path, data),
  del: (path) => request('DELETE', path),
  uploadFile
};
