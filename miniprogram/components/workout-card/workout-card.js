// 训练动作卡片组件：展示动作名、组数、重量、完成勾选
Component({
  properties: {
    exercise: { type: Object, value: {} },
    index: { type: Number, value: 0 }
  },

  data: {
    done: false
  },

  methods: {
    // 切换完成状态并向父组件通知
    onToggleDone() {
      const done = !this.data.done;
      this.setData({ done });
      this.triggerEvent('toggle', { index: this.properties.index, done });
    }
  }
});
