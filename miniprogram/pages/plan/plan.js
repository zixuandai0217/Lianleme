// 训练计划页：周视图Tab + 动作列表 + 难度调节
const api = require('../../utils/api');

Page({
  data: {
    weekDays: ['一', '二', '三', '四', '五', '六', '日'],
    selectedDay: 0,
    currentPlan: null,
    exercises: [],
    intensityLevel: 50,
    loading: false,
    adjustFeedback: ''
  },

  onLoad() {
    const today = new Date().getDay();
    // 将周日(0)映射为索引6，周一(1)映射为索引0
    const idx = today === 0 ? 6 : today - 1;
    this.setData({ selectedDay: idx });
    this.loadWeekPlan();
  },

  // 加载本周训练计划
  async loadWeekPlan() {
    this.setData({ loading: true });
    try {
      const res = await api.get('/api/plan');
      if (res.plan) {
        this.setData({ currentPlan: res.plan });
        this.loadDayExercises(this.data.selectedDay);
      }
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 切换星期Tab
  onDaySelect(e) {
    const idx = parseInt(e.currentTarget.dataset.index);
    this.setData({ selectedDay: idx });
    this.loadDayExercises(idx);
  },

  // 加载指定天的动作列表
  loadDayExercises(dayIndex) {
    const { currentPlan } = this.data;
    if (!currentPlan || !currentPlan.days) return;
    const dayData = currentPlan.days[dayIndex];
    this.setData({ exercises: dayData ? dayData.exercises : [] });
  },

  // 强度滑块变化
  onIntensityChange(e) {
    this.setData({ intensityLevel: e.detail.value });
  },

  // 提交难度调整
  async onAdjustIntensity() {
    const { intensityLevel } = this.data;
    wx.showLoading({ title: 'AI 调整中...' });
    try {
      const res = await api.post('/api/plan/adjust', { intensity: intensityLevel });
      this.setData({
        adjustFeedback: res.feedback || '计划已更新',
        currentPlan: res.plan
      });
      this.loadDayExercises(this.data.selectedDay);
      wx.showToast({ title: '计划已调整', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: '调整失败', icon: 'none' });
    } finally {
      wx.hideLoading();
    }
  },

  // 开始今日训练，跳转陪练页
  onStartWorkout() {
    wx.navigateTo({ url: '/pages/coach/coach' });
  }
});
