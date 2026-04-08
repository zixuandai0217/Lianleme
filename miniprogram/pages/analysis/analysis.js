// 体型分析页：拍照/上传 → 异步分析 → 结果展示
const { request, uploadImage } = require('../../utils/api');
const app = getApp();

Page({
  data: {
    imageUrl: '',
    imageBase64: '',
    status: 'idle',   // idle / uploading / processing / completed / failed
    taskId: '',
    result: null,
    pollTimer: null,
  },

  onUnload() {
    if (this.data.pollTimer) clearInterval(this.data.pollTimer);
  },

  // 选择图片（相机或相册）
  chooseImage(e) {
    const sourceType = e.currentTarget.dataset.source === 'camera'
      ? ['camera'] : ['album'];
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType,
      success: (res) => {
        const path = res.tempFiles[0].tempFilePath;
        this.setData({ imageUrl: path, status: 'idle', result: null });
        // 转 base64
        const fs = wx.getFileSystemManager();
        fs.readFile({
          filePath: path,
          encoding: 'base64',
          success: (r) => this.setData({ imageBase64: r.data }),
        });
      },
    });
  },

  // 开始分析
  async startAnalysis() {
    if (!this.data.imageBase64) {
      wx.showToast({ title: '请先选择照片', icon: 'none' });
      return;
    }
    this.setData({ status: 'uploading' });
    try {
      const userId = app.globalData.userId;
      const res = await request('/api/vision/analyze', 'POST', {
        image_base64: this.data.imageBase64,
        user_id: userId,
      });
      this.setData({ status: 'processing', taskId: res.task_id });
      this.startPolling(res.task_id);
    } catch (e) {
      this.setData({ status: 'failed' });
      wx.showToast({ title: '上传失败，请重试', icon: 'none' });
    }
  },

  // 轮询分析结果
  startPolling(taskId) {
    const timer = setInterval(async () => {
      try {
        const res = await request(`/api/vision/analyze/${taskId}`);
        if (res.status === 'completed') {
          clearInterval(timer);
          this.setData({ status: 'completed', result: res.result });
          // 自动生成训练计划
          this.generatePlan(res.result);
        } else if (res.status === 'failed') {
          clearInterval(timer);
          this.setData({ status: 'failed' });
          wx.showToast({ title: '分析失败，请重试', icon: 'none' });
        }
      } catch (e) {
        clearInterval(timer);
        this.setData({ status: 'failed' });
      }
    }, 2000);
    this.data.pollTimer = timer;
  },

  // 基于分析结果自动生成训练计划
  async generatePlan(analysis) {
    try {
      await request('/api/plan/generate', 'POST', {
        user_id: app.globalData.userId,
        body_analysis: analysis,
      });
      wx.showToast({ title: '训练计划已生成！', icon: 'success' });
    } catch (e) {
      console.warn('计划生成失败', e);
    }
  },

  retryAnalysis() {
    this.setData({ status: 'idle', result: null, taskId: '' });
  },
});
