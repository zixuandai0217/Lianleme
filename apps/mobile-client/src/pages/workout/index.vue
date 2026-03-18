<template>
  <view class="page">
    <view class="hero card">
      <text class="title">嗨，今天练了么？</text>
      <text class="sub">今日计划：胸背力量强化训练 · 45 分钟</text>
      <button class="pill-btn cta">开始训练</button>
    </view>

    <view class="calendar card">
      <text class="section-title">训练日历</text>
      <text class="sub">本周已完成 4/5 次训练</text>
    </view>

    <view class="coach card">
      <text class="section-title">AI 搭子</text>
      <text class="sub">给你今天的训练节奏和饮食提醒</text>
      <button class="pill-btn cta" @click="goCoach">立即咨询</button>
    </view>
  </view>
</template>

<script setup>
const goCoach = () => {
  uni.navigateTo({ url: '/pages/workout/ai-chat' })
}
</script>

<style scoped lang="scss">
.page { padding: 24rpx; display: grid; gap: 20rpx; }
.hero,.calendar,.coach { padding: 28rpx; }
.title { font-size: 40rpx; font-weight: 700; color: #1c2233; display: block; }
.section-title { font-size: 32rpx; font-weight: 700; color: #1c2233; display: block; }
.sub { margin-top: 10rpx; color: #6e7485; display: block; }
.cta { margin-top: 18rpx; font-size: 28rpx; }
</style>
