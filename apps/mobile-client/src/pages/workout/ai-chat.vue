<template>
  <view class="chat-page">
    <view class="card chat-box">
      <text class="hint">AI 搭子已接入：deepseek-v3.2（文本）</text>
      <view class="msg ai">今天建议先热身10分钟，再做上肢力量训练。</view>
      <view class="msg user">给我一个减脂训练安排</view>
      <view class="msg ai">每周 4 次：2 次力量 + 2 次有氧，饮食注意高蛋白。</view>
    </view>
  </view>
</template>

<script setup>
</script>

<style scoped lang="scss">
.chat-page { padding: 24rpx; }
.chat-box { padding: 24rpx; display: grid; gap: 16rpx; }
.hint { color: #6e7485; font-size: 24rpx; }
.msg { padding: 16rpx 20rpx; border-radius: 18rpx; }
.ai { background: #ffe7f0; color: #1c2233; }
.user { background: #f21162; color: #fff; justify-self: end; }
</style>
