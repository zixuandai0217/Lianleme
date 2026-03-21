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
import { onMounted } from 'vue'

import { requireMobileAuth } from '../../lib/authSession'

// guard the static AI chat demo behind the same mobile session gate as other business pages; workout AI chat access only; verify by opening the page without login in mini-program preview.
onMounted(() => {
  requireMobileAuth()
})
</script>

<style scoped lang="scss">
/* Why: keep chat page readable on H5 by providing px fallback where rpx may be ignored. */
/* Scope: workout AI chat spacing/typography only. */
/* Verify: bubbles and hint text no longer collapse into unstyled compact lines on 5173. */
.chat-page { padding: 24px; padding: 24rpx; }
.chat-box { padding: 24px; padding: 24rpx; display: grid; gap: 16px; gap: 16rpx; }
.hint { color: #6e7485; font-size: 24px; font-size: 24rpx; }
.msg { padding: 16px 20px; padding: 16rpx 20rpx; border-radius: 18px; border-radius: 18rpx; }
.ai { background: #ffe7f0; color: #1c2233; }
.user { background: #f21162; color: #fff; justify-self: end; }
</style>
