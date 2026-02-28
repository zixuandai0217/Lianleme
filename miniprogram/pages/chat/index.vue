<template>
  <view class="chat-container">
    <!-- 消息列表 -->
    <scroll-view
      class="message-list"
      scroll-y
      :scroll-into-view="scrollToView"
      :scroll-with-animation="true"
    >
      <view class="message-item" v-for="(msg, index) in messages" :key="index" :id="'msg-' + index">
        <!-- AI 消息 -->
        <view class="message-row ai" v-if="msg.role === 'assistant'">
          <view class="avatar ai-avatar">🤖</view>
          <view class="message-bubble ai-bubble">
            <text class="message-text">{{ msg.content }}</text>
          </view>
        </view>

        <!-- 用户消息 -->
        <view class="message-row user" v-else-if="msg.role === 'user'">
          <view class="message-bubble user-bubble">
            <text class="message-text">{{ msg.content }}</text>
          </view>
          <view class="avatar user-avatar">👤</view>
        </view>
      </view>

      <!-- 欢迎语 -->
      <view class="welcome-message" v-if="messages.length === 0">
        <view class="welcome-avatar">🤖</view>
        <view class="welcome-bubble">
          <text>你好！我是你的 AI 健康顾问～</text>
          <text>有什么关于减肥、健身、营养的问题都可以问我哦！</text>
        </view>
      </view>

      <!-- 正在输入 -->
      <view class="typing-indicator" v-if="isTyping">
        <view class="typing-dot"></view>
        <view class="typing-dot"></view>
        <view class="typing-dot"></view>
      </view>
    </scroll-view>

    <!-- 输入区域 -->
    <view class="input-area">
      <!-- 快捷问题 -->
      <scroll-view class="quick-questions" scroll-x v-if="messages.length === 0">
        <view class="question-chip" v-for="(q, i) in quickQuestions" :key="i" @click="sendQuickQuestion(q)">
          {{ q }}
        </view>
      </scroll-view>

      <view class="input-wrapper">
        <input
          v-model="inputText"
          type="text"
          placeholder="输入你的问题..."
          class="input-field"
          @confirm="sendMessage"
        />
        <button class="send-btn" @click="sendMessage" :disabled="!inputText.trim()">
          <text class="send-icon">📤</text>
        </button>
      </view>
    </view>
  </view>
</template>

<script>
import { ref, computed, nextTick, onMounted } from 'vue'
import { chatApi } from '@/api'
import { showError } from '@/utils'

export default {
  name: 'ChatIndex',
  setup() {
    const messages = ref([])
    const inputText = ref('')
    const isTyping = ref(false)
    const scrollToView = ref('')
    const sessionId = ref('session_' + Date.now())

    const quickQuestions = [
      '每天应该摄入多少卡路里？',
      '如何快速减掉肚子上的脂肪？',
      '运动后多久吃饭比较好？',
      '减肥期间可以吃水果吗？',
      '如何突破减肥平台期？'
    ]

    const sendMessage = async (text) => {
      const message = text || inputText.value.trim()
      if (!message) return

      // 添加用户消息
      messages.value.push({
        role: 'user',
        content: message
      })

      inputText.value = ''
      isTyping.value = true

      // 滚动到底部
      await nextTick()
      scrollToView.value = 'msg-' + (messages.value.length - 1)

      try {
        const response = await chatApi.send(sessionId.value, message)

        isTyping.value = false

        // 添加 AI 回复
        messages.value.push({
          role: 'assistant',
          content: response.reply
        })

        // 更新会话 ID
        if (response.session_id) {
          sessionId.value = response.session_id
        }

        // 滚动到底部
        await nextTick()
        scrollToView.value = 'msg-' + (messages.value.length - 1)
      } catch (error) {
        isTyping.value = false
        showError(error.message || '发送失败')
      }
    }

    const sendQuickQuestion = (question) => {
      sendMessage(question)
    }

    onMounted(() => {
      // 可以在这里加载历史消息
    })

    return {
      messages,
      inputText,
      isTyping,
      scrollToView,
      quickQuestions,
      sendMessage,
      sendQuickQuestion
    }
  }
}
</script>

<style lang="scss" scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: var(--bg-color);
}

.message-list {
  flex: 1;
  padding: 20rpx;
  overflow-y: auto;
}

.message-item {
  margin-bottom: 24rpx;
}

.message-row {
  display: flex;
  align-items: flex-start;

  &.ai {
    .avatar {
      margin-right: 16rpx;
    }

    .message-bubble {
      max-width: 70%;
      background-color: #FFFFFF;
      border-radius: 16rpx 16rpx 16rpx 4rpx;
    }
  }

  &.user {
    flex-direction: row-reverse;

    .avatar {
      margin-left: 16rpx;
    }

    .message-bubble {
      max-width: 70%;
      background: linear-gradient(135deg, #FF8A65, #FFAB91);
      border-radius: 16rpx 16rpx 4rpx 16rpx;

      .message-text {
        color: #FFFFFF;
      }
    }
  }

  .avatar {
    width: 72rpx;
    height: 72rpx;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 36rpx;
    flex-shrink: 0;

    &.ai-avatar {
      background-color: #E3F2FD;
    }

    &.user-avatar {
      background-color: #FFE0B2;
    }
  }

  .message-bubble {
    padding: 20rpx 24rpx;
    box-shadow: var(--shadow-card);

    .message-text {
      font-size: 28rpx;
      line-height: 1.6;
      color: var(--text-primary);
      word-break: break-all;
    }
  }
}

.welcome-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60rpx 40rpx;

  .welcome-avatar {
    font-size: 80rpx;
    margin-bottom: 24rpx;
  }

  .welcome-bubble {
    background-color: #FFFFFF;
    padding: 32rpx;
    border-radius: 16rpx;
    box-shadow: var(--shadow-card);

    text {
      display: block;
      font-size: 28rpx;
      color: var(--text-primary);
      line-height: 1.8;
      text-align: center;
    }
  }
}

.typing-indicator {
  display: flex;
  align-items: center;
  padding: 20rpx;
  gap: 8rpx;

  .typing-dot {
    width: 16rpx;
    height: 16rpx;
    border-radius: 50%;
    background-color: var(--text-hint);
    animation: typing 1.4s infinite;

    &:nth-child(2) {
      animation-delay: 0.2s;
    }

    &:nth-child(3) {
      animation-delay: 0.4s;
    }
  }
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-10rpx);
    opacity: 1;
  }
}

.input-area {
  border-top: 1rpx solid var(--border-color);
  background-color: #FFFFFF;
  padding-bottom: env(safe-area-inset-bottom);
}

.quick-questions {
  display: flex;
  padding: 16rpx 20rpx;
  border-bottom: 1rpx solid var(--border-color);

  .question-chip {
    flex-shrink: 0;
    padding: 12rpx 24rpx;
    background-color: #FFF8E5;
    border-radius: 24rpx;
    font-size: 24rpx;
    color: var(--color-primary);
    margin-right: 16rpx;
    border: 1rpx solid var(--border-color);

    &:active {
      background-color: var(--color-primary);
      color: #FFFFFF;
    }
  }
}

.input-wrapper {
  display: flex;
  align-items: center;
  padding: 20rpx;
  gap: 16rpx;

  .input-field {
    flex: 1;
    height: 80rpx;
    padding: 0 24rpx;
    background-color: #F5F5F5;
    border-radius: 40rpx;
    font-size: 28rpx;
  }

  .send-btn {
    width: 80rpx;
    height: 80rpx;
    border-radius: 50%;
    background: linear-gradient(135deg, #FF8A65, #FFAB91);
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;

    .send-icon {
      font-size: 32rpx;
    }

    &:disabled {
      opacity: 0.5;
    }
  }
}
</style>
