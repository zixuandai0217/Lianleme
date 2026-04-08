// AI 陪练对话页：聊天气泡 UI + 流式消息 + 训练上下文
const { request, streamRequest } = require('../../utils/api');
const app = getApp();

Page({
  data: {
    messages: [],
    inputText: '',
    currentExercise: '',
    completedSets: 0,
    totalSets: 0,
    planId: null,
    scrollToId: '',
    sending: false,
    quickReplies: ['完成一组', '换个动作', '怎么做', '太累了'],
  },

  onLoad(options) {
    if (options.planId) this.setData({ planId: Number(options.planId) });
    this.loadTodayContext();
    this.addMessage('ai', '嘿！我是你的AI健身搭子 💪 今天练什么，开始吧！');
  },

  async loadTodayContext() {
    try {
      const userId = app.globalData.userId;
      const today = await request(`/api/plan/${userId}/today`);
      if (today && today.exercises && today.exercises.length > 0) {
        this.setData({
          currentExercise: today.exercises[0].name,
          totalSets: today.exercises.reduce((s, e) => s + e.sets, 0),
        });
      }
    } catch (e) { console.warn('加载训练上下文失败', e); }
  },

  addMessage(role, text) {
    const messages = this.data.messages;
    const id = `msg_${Date.now()}`;
    messages.push({ id, role, text, time: new Date().toLocaleTimeString() });
    this.setData({ messages, scrollToId: id });
  },

  onInputChange(e) {
    this.setData({ inputText: e.detail.value });
  },

  async sendMessage(text) {
    const msg = text || this.data.inputText.trim();
    if (!msg || this.data.sending) return;
    this.setData({ inputText: '', sending: true });
    this.addMessage('user', msg);

    try {
      const res = await request('/api/coach/chat', 'POST', {
        user_id: app.globalData.userId,
        message: msg,
        current_exercise: this.data.currentExercise,
        completed_sets: this.data.completedSets,
        total_sets: this.data.totalSets,
        plan_id: this.data.planId,
      });
      this.addMessage('ai', res.reply);
      if (res.suggested_actions && res.suggested_actions.length) {
        this.setData({ quickReplies: res.suggested_actions });
      }
    } catch (e) {
      this.addMessage('ai', '网络波动，再试一次吧 🙏');
    } finally {
      this.setData({ sending: false });
    }
  },

  sendQuickReply(e) {
    const text = e.currentTarget.dataset.text;
    this.sendMessage(text);
    if (text === '完成一组') {
      this.setData({ completedSets: this.data.completedSets + 1 });
    }
  },

  sendInput() {
    this.sendMessage();
  },
});
