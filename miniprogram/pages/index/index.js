// 首页：今日训练任务 + 打卡入口 + 连续天数
const { request } = require('../../utils/api');
const app = getApp();

Page({
  data: {
    greeting: '',
    streak: 0,
    todayWorkout: null,
    completedSets: 0,
    isRestDay: false,
    weekCheckins: [],  // 本周7天打卡状态
  },

  onLoad() {
    this.setGreeting();
    this.loadTodayData();
  },

  onShow() {
    this.loadTodayData();
  },

  setGreeting() {
    const hour = new Date().getHours();
    let greeting = '嗨，练起来！';
    if (hour < 12) greeting = '早上好，来一发！';
    else if (hour < 18) greeting = '下午好，冲冲冲！';
    else greeting = '晚上好，夜练最专注！';
    this.setData({ greeting });
  },

  async loadTodayData() {
    const userId = app.globalData.userId;
    if (!userId) return;
    try {
      const [today, stats] = await Promise.all([
        request(`/api/plan/${userId}/today`),
        request(`/api/workout/${userId}/stats`),
      ]);
      this.setData({
        todayWorkout: today.is_rest_day ? null : today,
        isRestDay: !!today.is_rest_day,
        streak: stats.streak_days || 0,
        completedSets: 0,
      });
      this.buildWeekCheckins(stats.recent_records || []);
    } catch (e) {
      console.warn('加载首页数据失败', e);
    }
  },

  buildWeekCheckins(records) {
    const today = new Date();
    const week = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const dateStr = d.toISOString().slice(0, 10);
      const checked = records.some(r => r.workout_date === dateStr);
      week.push({ date: d.getDate(), checked, isToday: i === 0 });
    }
    this.setData({ weekCheckins: week });
  },

  goStartWorkout() {
    wx.navigateTo({ url: '/pages/coach/coach' });
  },

  goAnalysis() {
    wx.navigateTo({ url: '/pages/analysis/analysis' });
  },

  goPlan() {
    wx.switchTab({ url: '/pages/plan/plan' });
  },
});
