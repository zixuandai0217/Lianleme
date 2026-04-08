// 个人中心页：用户档案、统计数据、API Key 配置、打卡日历
const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    stats: { totalDays: 0, totalMinutes: 0, monthRate: 0 },
    profile: { height: 170, weight: 65, goal: 'gain_muscle', experience: 'beginner' },
    goalOptions: ['增肌', '减脂', '塑形', '提升耐力'],
    goalValues: ['gain_muscle', 'lose_fat', 'shaping', 'endurance'],
    goalIndex: 0,
    expOptions: ['新手（< 6个月）', '初级（6-18个月）', '中级（1.5-3年）', '进阶（3年以上）'],
    expValues: ['beginner', 'intermediate', 'advanced', 'expert'],
    expIndex: 0,
    calendarDays: [],
    currentMonth: '',
    apiKey: '',
    apiKeyMasked: '',
    hasApiKey: false,
    apiProvider: 'openai',
    showApiKeyInput: false,
    saving: false
  },

  onLoad() {
    this.loadUserInfo();
    this.buildCalendar();
  },

  // 加载用户信息与统计
  async loadUserInfo() {
    const token = auth.getToken();
    if (!token) {
      wx.navigateTo({ url: '/pages/index/index' });
      return;
    }
    try {
      const res = await api.get('/api/user/profile');
      const { user, stats } = res;
      const goalIndex = this.data.goalValues.indexOf(user.goal || 'gain_muscle');
      const expIndex = this.data.expValues.indexOf(user.experience || 'beginner');
      this.setData({
        userInfo: user,
        stats: stats || this.data.stats,
        profile: {
          height: user.height || 170,
          weight: user.weight || 65,
          goal: user.goal || 'gain_muscle',
          experience: user.experience || 'beginner'
        },
        goalIndex: goalIndex >= 0 ? goalIndex : 0,
        expIndex: expIndex >= 0 ? expIndex : 0,
        hasApiKey: !!user.has_api_key,
        apiProvider: user.llm_provider || 'openai'
      });
    } catch (e) {
      console.error('加载用户信息失败', e);
    }
  },

  // 构建本月打卡日历
  buildCalendar() {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = now.getDate();
    // 模拟打卡数据，实际应从后端获取
    const checkedDays = new Set();
    const days = [];
    for (let d = 1; d <= daysInMonth; d++) {
      days.push({ day: d, checked: checkedDays.has(d), isToday: d === today, isFuture: d > today });
    }
    this.setData({
      calendarDays: days,
      currentMonth: `${year}年${month + 1}月`
    });
  },

  // 身高滑块
  onHeightChange(e) {
    this.setData({ 'profile.height': e.detail.value });
  },

  // 体重滑块
  onWeightChange(e) {
    this.setData({ 'profile.weight': e.detail.value });
  },

  // 目标选择
  onGoalChange(e) {
    const idx = parseInt(e.detail.value);
    this.setData({ goalIndex: idx, 'profile.goal': this.data.goalValues[idx] });
  },

  // 训练经验选择
  onExpChange(e) {
    const idx = parseInt(e.detail.value);
    this.setData({ expIndex: idx, 'profile.experience': this.data.expValues[idx] });
  },

  // 保存档案
  async onSaveProfile() {
    this.setData({ saving: true });
    try {
      await api.post('/api/user/profile', this.data.profile);
      wx.showToast({ title: '保存成功', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  },

  // 切换 API Key 输入框显示
  onToggleApiKeyInput() {
    this.setData({ showApiKeyInput: !this.data.showApiKeyInput });
  },

  // API Key 输入
  onApiKeyInput(e) {
    this.setData({ apiKey: e.detail.value });
  },

  // 切换 API 提供商
  onProviderChange(e) {
    this.setData({ apiProvider: e.currentTarget.dataset.provider });
  },

  // 保存 API Key
  async onSaveApiKey() {
    const { apiKey, apiProvider } = this.data;
    if (!apiKey.trim()) {
      wx.showToast({ title: '请输入 API Key', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '保存中...' });
    try {
      await api.post('/api/user/api-key', { api_key: apiKey, provider: apiProvider });
      this.setData({
        hasApiKey: true,
        apiKeyMasked: apiKey.substring(0, 6) + '****',
        apiKey: '',
        showApiKeyInput: false
      });
      wx.showToast({ title: '已保存', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      wx.hideLoading();
    }
  },

  // 清除 API Key，恢复使用系统默认
  async onClearApiKey() {
    wx.showModal({
      title: '确认清除',
      content: '清除后将使用系统默认 Key',
      success: async (res) => {
        if (res.confirm) {
          await api.post('/api/user/api-key/clear', {});
          this.setData({ hasApiKey: false, apiKeyMasked: '' });
          wx.showToast({ title: '已清除', icon: 'success' });
        }
      }
    });
  },

  // 退出登录
  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定退出当前账号？',
      success: (res) => {
        if (res.confirm) {
          auth.clearToken();
          wx.reLaunch({ url: '/pages/index/index' });
        }
      }
    });
  }
});
