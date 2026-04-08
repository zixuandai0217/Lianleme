// 小程序全局 App 实例，初始化登录态
const { login } = require('./utils/auth');

App({
  globalData: {
    userInfo: null,
    token: null,
    userId: null,
    baseUrl: 'http://localhost:8000',
  },

  onLaunch() {
    // 启动时自动登录
    login().then((res) => {
      this.globalData.token = res.token;
      this.globalData.userId = res.user_id;
    }).catch(console.error);
  },
});
