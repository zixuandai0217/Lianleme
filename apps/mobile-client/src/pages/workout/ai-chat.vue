<template>
  <!-- upgrade the static AI buddy placeholder into a designed coaching conversation surface while keeping the data local and demo-safe; workout AI chat experience only; verify with build:h5 and node tests/e2e/mobile_surface_contract.mjs. -->
  <view class="chat-page app-mobile-page">
    <view class="coach-chat-shell app-mobile-shell app-mobile-shell--aurora">
      <view class="coach-chat-topbar">
        <view>
          <text class="app-mobile-section-kicker">AI COACH ROOM</text>
          <text class="coach-chat-title">今晚的训练我来陪你</text>
          <text class="coach-chat-subtitle">当前会话账号：{{ sessionAccountLabel }}</text>
        </view>
        <view class="coach-chip">深度陪练</view>
      </view>

      <view class="coach-presence-card app-mobile-signal-card">
        <view class="coach-presence-copy">
          <text class="coach-presence-label">deepseek-v3.2</text>
          <text class="coach-presence-title">AI 搭子已准备好训练安排、饮食提醒和情绪拉回。</text>
          <text class="coach-presence-note">当前还是演示对话流，但信息层级和动作反馈已经按 APK 体验设计。</text>
        </view>

        <view class="coach-presence-avatar">
          <view class="coach-presence-halo"></view>
          <view class="coach-presence-core">AI</view>
        </view>
      </view>

      <view class="coach-suggestion-row">
        <view
          v-for="prompt in quickPrompts"
          :key="prompt"
          class="coach-suggestion-chip"
          @click="handlePrompt(prompt)"
        >
          {{ prompt }}
        </view>
      </view>

      <view class="message-stack">
        <view
          v-for="message in messages"
          :key="message.id"
          class="message-card"
          :class="message.role === 'user' ? 'message-card--user' : 'message-card--ai'"
        >
          <text class="message-role">{{ message.role === 'user' ? '你' : 'AI 搭子' }}</text>
          <text class="message-text">{{ message.text }}</text>
        </view>
      </view>

      <view class="coach-footer-grid">
        <view class="app-mobile-floating-note">
          <strong>训练建议</strong>
          <span>力量优先，最后追加 12 分钟中低强度收尾有氧。</span>
        </view>
        <view class="app-mobile-floating-note">
          <strong>饮食提醒</strong>
          <span>训练后 1 小时内补蛋白和主食，避免纯空腹硬撑。</span>
        </view>
      </view>

      <view class="composer-shell">
        <view class="composer-copy">
          <text class="composer-label">继续追问 AI 搭子</text>
          <text class="composer-hint">例如：给我一版只需要 30 分钟的减脂训练。</text>
        </view>
        <view class="composer-action" @click="handlePrompt('给我一版 30 分钟减脂训练')">发送演示提问</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { loadMobileSession, requireMobileAuth } from '../../lib/authSession'

const session = ref(loadMobileSession())

const quickPrompts = [
  '今晚练什么最合适',
  '晚饭怎么吃更稳',
  '如果没状态怎么开始',
]

const messages = [
  {
    id: 'ai-1',
    role: 'ai',
    text: '今晚建议先做 8 分钟热身，把心率和关节活动度提起来，再进入上肢力量主训练。',
  },
  {
    id: 'user-1',
    role: 'user',
    text: '我今天只有 40 分钟，而且昨天已经练过腿了。',
  },
  {
    id: 'ai-2',
    role: 'ai',
    text: '那就做胸背推拉 + 核心稳定，主训练控制在 28 分钟，最后用 6 分钟收尾拉伸。',
  },
]

const sessionAccountLabel = computed(() => {
  // keep the chat page identity aligned with the local mobile session so APK demos feel coherent without adding new auth contracts; AI chat identity display only; verify with build:h5 and the mobile surface contract script.
  return session.value?.email || session.value?.phone || '演示账号'
})

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const handlePrompt = (prompt) => {
  showToast(`演示提问已记录：${prompt}`)
}

// guard the designed AI chat demo behind the same mobile session gate as other business pages; workout AI chat access only; verify by opening the page without login in mini-program preview.
onMounted(() => {
  const activeSession = requireMobileAuth()
  if (activeSession) {
    session.value = activeSession
  }
})
</script>

<style scoped lang="scss">
/* restyle the AI chat page into a conversation-first coaching room while keeping interactions local and non-destructive; workout AI chat layout only; verify with build:h5 and node tests/e2e/mobile_surface_contract.mjs. */
/* keep the chat-page box-sizing reset mp-weixin-safe by targeting supported uni elements instead of scoped universal selectors; ai chat layout only; verify with `npm --workspace apps/mobile-client run build:mp-weixin && node tests/e2e/mobile_mp_style_contract.mjs`. */
.chat-page,
.chat-page view,
.chat-page text,
.chat-page button,
.chat-page input,
.chat-page textarea,
.chat-page image,
.chat-page navigator,
.chat-page scroll-view,
.chat-page swiper,
.chat-page swiper-item {
  box-sizing: border-box;
}

.chat-page {
  min-height: 100vh;
  padding-top: 20px;
}

.coach-chat-shell {
  display: grid;
  gap: 16px;
}

.coach-chat-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.coach-chat-title {
  display: block;
  margin-top: 10px;
  font-size: 32px;
  line-height: 0.98;
  font-weight: 900;
  color: var(--mobile-ink);
}

.coach-chat-subtitle {
  display: block;
  margin-top: 10px;
  color: #6b7287;
}

.coach-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 16px;
  border-radius: 999px;
  background: rgba(28, 34, 51, 0.06);
  color: #f0644d;
  font-weight: 800;
}

.coach-presence-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
}

.coach-presence-copy {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 10px;
  max-width: 230px;
}

.coach-presence-label {
  font-size: 11px;
  letter-spacing: 1.8px;
  color: rgba(255, 255, 255, 0.68);
  font-weight: 800;
}

.coach-presence-title {
  display: block;
  font-size: 24px;
  line-height: 1.05;
  font-weight: 900;
}

.coach-presence-note {
  display: block;
  color: rgba(255, 255, 255, 0.74);
  line-height: 1.55;
}

.coach-presence-avatar {
  position: relative;
  width: 108px;
  height: 108px;
  flex-shrink: 0;
}

.coach-presence-halo,
.coach-presence-core {
  position: absolute;
  inset: 0;
  border-radius: 32px;
}

.coach-presence-halo {
  border: 1px solid rgba(255, 255, 255, 0.16);
  transform: rotate(-12deg);
}

.coach-presence-core {
  inset: 16px;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 28px;
  font-weight: 900;
  background: linear-gradient(145deg, rgba(255, 130, 84, 0.76), rgba(242, 17, 98, 0.7));
}

.coach-suggestion-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.coach-suggestion-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.76);
  color: var(--mobile-ink);
  font-size: 13px;
  font-weight: 800;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.94),
    0 10px 22px rgba(28, 34, 51, 0.08);
}

.message-stack {
  display: grid;
  gap: 12px;
}

.message-card {
  display: grid;
  gap: 8px;
  max-width: 88%;
  padding: 16px 18px;
  border-radius: 24px;
}

.message-card--ai {
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(247, 248, 252, 0.94));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.92),
    0 14px 24px rgba(28, 34, 51, 0.08);
}

.message-card--user {
  margin-left: auto;
  color: #fff;
  background: linear-gradient(145deg, #f21162, #ff7a45);
  box-shadow: 0 16px 28px rgba(242, 17, 98, 0.18);
}

.message-role {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1.4px;
  opacity: 0.76;
}

.message-text {
  line-height: 1.7;
}

.coach-footer-grid {
  display: grid;
  gap: 12px;
}

.composer-shell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  border-radius: 24px;
  background: rgba(28, 34, 51, 0.06);
}

.composer-copy {
  display: grid;
  gap: 6px;
}

.composer-label {
  font-size: 16px;
  font-weight: 800;
  color: var(--mobile-ink);
}

.composer-hint {
  color: #6d7487;
  line-height: 1.55;
  font-size: 13px;
}

.composer-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 46px;
  padding: 0 18px;
  border-radius: 999px;
  color: #fff;
  font-weight: 800;
  white-space: nowrap;
  background: var(--mobile-brand-gradient);
  box-shadow: 0 14px 26px rgba(242, 17, 98, 0.18);
}

@media (max-width: 420px) {
  .coach-chat-topbar,
  .coach-presence-card,
  .composer-shell {
    flex-direction: column;
    align-items: flex-start;
  }

  .coach-presence-copy,
  .message-card {
    max-width: none;
  }

  .composer-action {
    width: 100%;
  }
}
</style>
