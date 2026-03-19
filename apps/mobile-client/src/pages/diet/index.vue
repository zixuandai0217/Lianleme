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
/* Why: add px fallback for H5 so diet page spacing and type scale render predictably. */
/* Scope: diet tab visual styles only; business content unchanged. */
/* Verify: cards and CTA on diet page appear with intended spacing at localhost:5173. */
.page { padding: 24px; padding: 24rpx; display: grid; gap: 20px; gap: 20rpx; }
.intake,.record { padding: 28px; padding: 28rpx; }
.title { font-size: 38px; font-size: 38rpx; font-weight: 700; display: block; }
.kcal { margin-top: 12px; margin-top: 12rpx; font-size: 42px; font-size: 42rpx; color: #f21162; display: block; font-weight: 700; }
.section-title { font-size: 32px; font-size: 32rpx; font-weight: 700; display: block; }
.sub { margin-top: 10px; margin-top: 10rpx; color: #6e7485; display: block; }
.cta { margin-top: 16px; margin-top: 16rpx; }
</style>
