<script>
export default {
  onLaunch: function() {
    console.log('VibeFit App Launch')
    // 初始化全局数据
    this.globalData = {
      API_BASE_URL: 'http://localhost:8000/api/v1',
      token: ''
    }
  },
  onShow: function() {
    console.log('VibeFit App Show')
  },
  onHide: function() {
    console.log('VibeFit App Hide')
  }
}
</script>

<style lang="scss">
/*每个页面公共 css*/
@import '@/uni.scss';

page {
  background-color: var(--bg-color);
}

/* 隐藏滚动条但保持滚动功能 */
::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
  color: transparent;
}
</style>
