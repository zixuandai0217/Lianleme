<template>
  <view class="page">
    <view class="card block">
      <text class="title">我的资料</text>
      <text class="sub">昵称、身高、体重、目标体重</text>
    </view>
    <view class="card block">
      <text class="title">设置</text>
      <text class="sub">通知、隐私、主题</text>
    </view>
    <view class="card block">
      <text class="title">数据导出</text>
      <text class="sub">导出训练与饮食记录</text>
    </view>
    <view class="card block">
      <text class="title">账号管理</text>
      <text class="sub">注销与登录设备管理</text>
    </view>
  </view>
</template>

<script setup>
</script>

<style scoped lang="scss">
/* Why: add px fallback for H5 to keep profile cards readable with current direct-entry runtime. */
/* Scope: profile page spacing/type styles only. */
/* Verify: profile page cards and text spacing are visibly styled on localhost:5173. */
.page { padding: 24px; padding: 24rpx; display: grid; gap: 16px; gap: 16rpx; }
.block { padding: 24px; padding: 24rpx; }
.title { font-size: 30px; font-size: 30rpx; font-weight: 700; display: block; }
.sub { margin-top: 8px; margin-top: 8rpx; color: #6e7485; display: block; }
</style>
