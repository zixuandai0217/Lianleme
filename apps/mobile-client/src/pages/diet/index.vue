<template>
  <view class="page">
    <view class="card intake">
      <text class="title">嗨，今天吃了么？</text>
      <text class="kcal">1200 / 2000 kcal</text>
      <text class="sub">蛋白质 125g · 碳水 180g · 脂肪 62g</text>
    </view>

    <view class="card record">
      <text class="section-title">今日饮食记录</text>
      <text class="sub">早餐 鸡蛋/全麦面包 · 午餐 鸡胸肉沙拉</text>
      <button class="pill-btn cta">记录晚餐</button>
    </view>
  </view>
</template>

<script setup>
</script>

<style scoped lang="scss">
.page { padding: 24rpx; display: grid; gap: 20rpx; }
.intake,.record { padding: 28rpx; }
.title { font-size: 38rpx; font-weight: 700; display: block; }
.kcal { margin-top: 12rpx; font-size: 42rpx; color: #f21162; display: block; font-weight: 700; }
.section-title { font-size: 32rpx; font-weight: 700; display: block; }
.sub { margin-top: 10rpx; color: #6e7485; display: block; }
.cta { margin-top: 16rpx; }
</style>
