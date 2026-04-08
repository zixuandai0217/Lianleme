// 微信登录与 token 本地存储封装
const api = require('./api');

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'user_info';

/**
 * 执行微信登录流程：wx.login → 后端 code2session → 存 token
 * @returns {Promise<object>} 用户信息
 */
function login() {
  return new Promise((resolve, reject) => {
    wx.login({
      success: async (res) => {
        if (!res.code) {
          reject(new Error('wx.login 失败'));
          return;
        }
        try {
          const data = await api.post('/api/user/login', { code: res.code });
          wx.setStorageSync(TOKEN_KEY, data.token);
          wx.setStorageSync(USER_KEY, data.user);
          resolve(data.user);
        } catch (e) {
          reject(e);
        }
      },
      fail: reject
    });
  });
}

/** 获取本地缓存的 token */
function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || null;
}

/** 获取本地缓存的用户信息 */
function getUserInfo() {
  return wx.getStorageSync(USER_KEY) || null;
}

/** 检查是否已登录（token 存在） */
function isLoggedIn() {
  return !!getToken();
}

/** 清除登录态 */
function clearToken() {
  wx.removeStorageSync(TOKEN_KEY);
  wx.removeStorageSync(USER_KEY);
}

/**
 * 确保已登录，未登录则自动触发登录流程
 * @returns {Promise<object>} 用户信息
 */
async function ensureLogin() {
  if (isLoggedIn()) {
    return getUserInfo();
  }
  return login();
}

module.exports = { login, getToken, getUserInfo, isLoggedIn, clearToken, ensureLogin };
