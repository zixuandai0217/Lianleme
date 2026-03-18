<template>
  <view class="page">
    <view class="card trend">
      <text class="title">嗨，今天瘦了么？</text>
      <text class="weight">71.1 kg</text>
      <text class="sub">较上周 -0.8 kg，继续保持。</text>
    </view>

    <view class="card report">
      <text class="section-title">周报摘要</text>
      <text class="sub">摄入 12,450 kcal · 消耗 3,850 kcal</text>
      <text class="sub">AI建议：本周可以再增加一次力量训练。</text>
    </view>

    <view class="card my-entry">
      <text class="section-title">我的</text>
      <text class="sub">资料、设置、导出、账号管理</text>
      <button class="pill-btn cta" @click="goMy">进入我的</button>
    </view>
  </view>
</template>

<script setup>
const goMy = () => {
  uni.navigateTo({ url: '/pages/profile/index' })
}
</script>

<style scoped lang="scss">
.page { padding: 24rpx; display: grid; gap: 20rpx; }
.trend,.report,.my-entry { padding: 28rpx; }
.title { font-size: 38rpx; font-weight: 700; display: block; }
.weight { margin-top: 12rpx; font-size: 44rpx; color: #ff7a45; display: block; font-weight: 700; }
.section-title { font-size: 32rpx; font-weight: 700; display: block; }
.sub { margin-top: 10rpx; color: #6e7485; display: block; }
.cta { margin-top: 16rpx; }
</style>
