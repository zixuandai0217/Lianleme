// 训练进度环形图组件：Canvas 绘制环形进度
Component({
  properties: {
    // 当前完成值
    current: { type: Number, value: 0 },
    // 总值
    total: { type: Number, value: 1 },
    // 环半径
    radius: { type: Number, value: 60 },
    // 线宽
    lineWidth: { type: Number, value: 8 },
    // 主色
    color: { type: String, value: '#00FF88' }
  },

  observers: {
    'current, total': function () {
      this.drawRing();
    }
  },

  methods: {
    // 使用 Canvas 2D API 绘制环形进度
    drawRing() {
      const { current, total, radius, lineWidth, color } = this.properties;
      const ratio = total > 0 ? current / total : 0;
      const query = this.createSelectorQuery();
      query.select('#ring-canvas')
        .fields({ node: true, size: true })
        .exec((res) => {
          if (!res[0] || !res[0].node) return;
          const canvas = res[0].node;
          const ctx = canvas.getContext('2d');
          const dpr = wx.getWindowInfo ? wx.getWindowInfo().pixelRatio : 2;
          const size = (radius * 2 + lineWidth * 2);
          canvas.width = size * dpr;
          canvas.height = size * dpr;
          ctx.scale(dpr, dpr);
          const cx = size / 2;
          const cy = size / 2;
          // 背景轨道
          ctx.beginPath();
          ctx.arc(cx, cy, radius, 0, Math.PI * 2);
          ctx.strokeStyle = '#2A2A2A';
          ctx.lineWidth = lineWidth;
          ctx.stroke();
          // 进度弧
          if (ratio > 0) {
            ctx.beginPath();
            ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * ratio);
            ctx.strokeStyle = color;
            ctx.lineWidth = lineWidth;
            ctx.lineCap = 'round';
            ctx.stroke();
          }
          // 中心文字
          ctx.fillStyle = '#FFFFFF';
          ctx.font = `bold ${radius * 0.4}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(`${current}/${total}`, cx, cy);
        });
    }
  }
});
