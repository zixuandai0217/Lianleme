<template>
  <view class="login-container">
    <!-- Logo 区域 -->
    <view class="logo-section">
      <view class="logo-icon">🍊</view>
      <view class="logo-text">VibeFit</view>
      <view class="logo-subtitle">AI 科学减肥健身</view>
    </view>

    <!-- 登录表单 -->
    <view class="login-form card">
      <view class="form-title">欢迎回来</view>

      <!-- 手机号输入 -->
      <view class="form-item">
        <view class="form-label">手机号</view>
        <view class="form-input-wrapper">
          <text class="input-prefix">+86</text>
          <input
            v-model="phone"
            type="number"
            maxlength="11"
            placeholder="请输入手机号"
            class="form-input"
          />
        </view>
      </view>

      <!-- 验证码输入 -->
      <view class="form-item">
        <view class="form-label">验证码</view>
        <view class="form-input-wrapper">
          <input
            v-model="code"
            type="number"
            maxlength="6"
            placeholder="请输入验证码"
            class="form-input"
          />
          <button
            class="code-btn"
            :disabled="countdown > 0"
            @click="sendCode"
          >
            {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
          </button>
        </view>
      </view>

      <!-- 登录按钮 -->
      <button class="login-btn" @click="handleLogin">
        登 录
      </button>

      <!-- 协议说明 -->
      <view class="agreement">
        <text>登录即代表您同意</text>
        <text class="link" @click.stop="showPrivacyNotice">《隐私保护说明》</text>
      </view>

      <!-- 隐私保护提示 -->
      <view class="privacy-hint" @click.stop="showPrivacyNotice">
        <text class="privacy-icon">🔒</text>
        <text class="privacy-text">隐私保护说明</text>
        <text class="privacy-arrow">›</text>
      </view>
    </view>

    <!-- 隐私保护弹窗 -->
    <view class="privacy-modal" v-if="showPrivacyModal" @click="closePrivacyModal">
      <view class="modal-content" @click.stop>
        <view class="modal-header">
          <text class="modal-title">🔒 隐私保护说明</text>
        </view>
        <scroll-view class="modal-body" scroll-y>
          <view class="privacy-section">
            <text class="section-title">我们收集的信息</text>
            <text class="section-content">
              为了提供个性化的减肥健身建议，我们会收集您主动提供的以下信息：
            </text>
            <view class="info-list">
              <text class="info-item">• 手机号（仅用于登录验证）</text>
              <text class="info-item">• 身体数据（身高、体重、体脂率等）</text>
              <text class="info-item">• 饮食和运动记录</text>
              <text class="info-item">• 健康目标和偏好设置</text>
            </view>
          </view>

          <view class="privacy-section">
            <text class="section-title">我们如何使用信息</text>
            <text class="section-content">
              您的信息仅用于：
            </text>
            <view class="info-list">
              <text class="info-item">✓ 生成个性化的饮食和运动计划</text>
              <text class="info-item">✓ 追踪您的身体数据变化趋势</text>
              <text class="info-item">✓ AI 健康顾问提供针对性建议</text>
              <text class="info-item">✓ 改善和优化我们的服务</text>
            </view>
          </view>

          <view class="privacy-section">
            <text class="section-title">隐私保护承诺</text>
            <view class="promise-list">
              <view class="promise-item">
                <text class="promise-icon">🛡️</text>
                <view class="promise-content">
                  <text class="promise-title">数据加密存储</text>
                  <text class="promise-desc">所有个人信息采用加密技术存储，防止未授权访问</text>
                </view>
              </view>
              <view class="promise-item">
                <text class="promise-icon">🔐</text>
                <view class="promise-content">
                  <text class="promise-title">不会泄露隐私</text>
                  <text class="promise-desc">我们不会向任何第三方出售或泄露您的个人信息</text>
                </view>
              </view>
              <view class="promise-item">
                <text class="promise-icon">👤</text>
                <view class="promise-content">
                  <text class="promise-title">匿名化处理</text>
                  <text class="promise-desc">AI 服务使用匿名标识，不会暴露您的真实身份</text>
                </view>
              </view>
              <view class="promise-item">
                <text class="promise-icon">🗑️</text>
                <view class="promise-content">
                  <text class="promise-title">可删除数据</text>
                  <text class="promise-desc">您可以随时申请删除所有个人数据</text>
                </view>
              </view>
            </view>
          </view>

          <view class="privacy-section">
            <text class="section-title">AI 服务说明</text>
            <text class="section-content">
              本应用使用 AI（通义千问）提供健康建议。在使用 AI 服务时：
            </text>
            <view class="info-list">
              <text class="info-item">• 仅发送必要的身体数据用于生成建议</text>
              <text class="info-item">• 不包含您的手机号、姓名等身份信息</text>
              <text class="info-item">• AI 服务商受保密协议约束</text>
              <text class="info-item">• 对话记录仅您可见</text>
            </view>
          </view>

          <view class="privacy-section">
            <text class="section-title">您的权利</text>
            <text class="section-content">
              您享有以下权利：
            </text>
            <view class="info-list">
              <text class="info-item">✓ 查看和导出您的所有数据</text>
              <text class="info-item">✓ 修改或删除您的个人信息</text>
              <text class="info-item">✓ 随时注销账号</text>
              <text class="info-item">✓ 投诉和反馈</text>
            </view>
          </view>

          <view class="privacy-section">
            <text class="section-title">联系我们</text>
            <text class="section-content">
              如有任何隐私相关问题，请通过以下方式联系我们：
            </text>
            <text class="contact-info">邮箱：privacy@vibefit.com</text>
          </view>

          <view class="privacy-note">
            <text>本隐私政策可能会不定期更新，请在每次使用前仔细阅读。</text>
            <text>最后更新日期：2024 年 1 月</text>
          </view>
        </scroll-view>
        <view class="modal-footer">
          <button class="agree-btn" @click="agreeAndClose">我已知晓并同意</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { authApi } from '@/api'
import { useUserStore } from '@/store'
import { showSuccess, showError } from '@/utils'

export default {
  name: 'Login',
  setup() {
    const userStore = useUserStore()

    const phone = ref('')
    const code = ref('')
    const countdown = ref(0)
    const isSending = ref(false)
    const showPrivacyModal = ref(false)
    const hasAgreedPrivacy = ref(false)

    // 显示隐私保护说明
    const showPrivacyNotice = () => {
      showPrivacyModal.value = true
    }

    // 关闭隐私保护弹窗
    const closePrivacyModal = () => {
      showPrivacyModal.value = false
    }

    // 同意并关闭
    const agreeAndClose = () => {
      hasAgreedPrivacy.value = true
      showPrivacyModal.value = false
      showSuccess('感谢信任，我们将严格保护您的隐私')
    }

    // 验证手机号
    const validatePhone = () => {
      if (!phone.value) {
        showError('请输入手机号')
        return false
      }
      if (!/^1[3-9]\d{9}$/.test(phone.value)) {
        showError('请输入正确的手机号')
        return false
      }
      return true
    }

    // 发送验证码
    const sendCode = async () => {
      if (!validatePhone() || isSending.value) return

      isSending.value = true
      try {
        const res = await authApi.getVerifyCode(phone.value)
        // 开发环境：自动填充验证码
        if (res?.code) {
          code.value = res.code
          showSuccess('验证码已填充（生产环境将发送短信）')
        }
        // 开始倒计时
        countdown.value = 60
        const timer = setInterval(() => {
          countdown.value--
          if (countdown.value <= 0) {
            clearInterval(timer)
          }
        }, 1000)
      } catch (error) {
        showError(error.message || '发送失败')
      } finally {
        isSending.value = false
      }
    }

    // 处理登录
    const handleLogin = async () => {
      if (!validatePhone()) return

      if (!code.value) {
        showError('请输入验证码')
        return
      }

      // 提示用户阅读隐私政策
      if (!hasAgreedPrivacy.value) {
        showPrivacyNotice()
        showError('请先阅读并同意隐私保护说明')
        return
      }

      try {
        const res = await authApi.login(phone.value, code.value)

        // 保存 token
        userStore.setToken(res.access_token)
        userStore.setUserInfo({
          id: res.user_id,
          nickname: res.nickname
        })

        showSuccess('登录成功')

        // 跳转到首页
        setTimeout(() => {
          uni.reLaunch({ url: '/pages/index/index' })
        }, 500)
      } catch (error) {
        showError(error.message || '登录失败')
      }
    }

    return {
      phone,
      code,
      countdown,
      showPrivacyModal,
      hasAgreedPrivacy,
      showPrivacyNotice,
      closePrivacyModal,
      agreeAndClose,
      sendCode,
      handleLogin
    }
  }
}
</script>

<style lang="scss" scoped>
.login-container {
  min-height: 100vh;
  background: linear-gradient(180deg, #FFF8E5 0%, #FFE0B2 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 120rpx;
}

.logo-section {
  text-align: center;
  margin-bottom: 80rpx;

  .logo-icon {
    font-size: 120rpx;
    margin-bottom: 24rpx;
  }

  .logo-text {
    font-size: 48rpx;
    font-weight: bold;
    color: var(--color-primary);
    margin-bottom: 12rpx;
  }

  .logo-subtitle {
    font-size: 28rpx;
    color: var(--text-secondary);
  }
}

.login-form {
  width: 90%;
  max-width: 640rpx;
  padding: 48rpx 32rpx;

  .form-title {
    font-size: 40rpx;
    font-weight: bold;
    color: var(--text-primary);
    text-align: center;
    margin-bottom: 48rpx;
  }

  .form-item {
    margin-bottom: 32rpx;

    .form-label {
      font-size: 28rpx;
      color: var(--text-primary);
      margin-bottom: 12rpx;
      font-weight: 500;
    }

    .form-input-wrapper {
      display: flex;
      align-items: center;
      border: 2rpx solid var(--border-color);
      border-radius: 16rpx;
      overflow: hidden;
      background-color: #FFFFFF;

      .input-prefix {
        padding: 24rpx 20rpx;
        font-size: 28rpx;
        color: var(--text-primary);
        border-right: 1rpx solid var(--border-color);
      }

      .form-input {
        flex: 1;
        padding: 24rpx 20rpx;
        font-size: 28rpx;
      }

      .code-btn {
        padding: 0 24rpx;
        height: 88rpx;
        line-height: 88rpx;
        font-size: 26rpx;
        color: var(--color-primary);
        background-color: transparent;
        border: none;
        border-left: 1rpx solid var(--border-color);

        &:disabled {
          color: var(--text-hint);
        }
      }
    }
  }

  .login-btn {
    width: 100%;
    height: 96rpx;
    line-height: 96rpx;
    background: linear-gradient(135deg, #FF8A65, #FFAB91);
    color: #FFFFFF;
    font-size: 32rpx;
    font-weight: bold;
    border-radius: 48rpx;
    border: none;
    margin-top: 48rpx;
    margin-bottom: 24rpx;

    &:active {
      opacity: 0.8;
    }
  }

  .agreement {
    text-align: center;
    font-size: 24rpx;
    color: var(--text-hint);

    .link {
      color: var(--color-primary);
      text-decoration: underline;
    }
  }

  .privacy-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8rpx;
    padding: 16rpx;
    margin-top: 16rpx;
    background-color: #FFF8E5;
    border-radius: 12rpx;
    font-size: 24rpx;
    color: var(--text-secondary);

    .privacy-icon {
      font-size: 28rpx;
    }

    .privacy-text {
      color: var(--color-primary);
    }

    .privacy-arrow {
      font-size: 28rpx;
      color: var(--text-hint);
    }
  }
}

.privacy-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;

  .modal-content {
    width: 90%;
    max-width: 640rpx;
    max-height: 80vh;
    background-color: #FFFFFF;
    border-radius: 24rpx;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    padding: 32rpx 24rpx;
    border-bottom: 1rpx solid var(--border-color);

    .modal-title {
      font-size: 32rpx;
      font-weight: bold;
      color: var(--text-primary);
    }
  }

  .modal-body {
    flex: 1;
    padding: 24rpx;
    max-height: 60vh;

    .privacy-section {
      margin-bottom: 32rpx;

      .section-title {
        font-size: 28rpx;
        font-weight: bold;
        color: var(--color-primary);
        display: block;
        margin-bottom: 12rpx;
      }

      .section-content {
        font-size: 26rpx;
        color: var(--text-secondary);
        line-height: 1.6;
        display: block;
        margin-bottom: 12rpx;
      }

      .info-list {
        display: flex;
        flex-direction: column;
        gap: 8rpx;

        .info-item {
          font-size: 24rpx;
          color: var(--text-secondary);
          line-height: 1.6;
        }
      }

      .promise-list {
        display: flex;
        flex-direction: column;
        gap: 16rpx;

        .promise-item {
          display: flex;
          align-items: flex-start;
          gap: 16rpx;
          padding: 16rpx;
          background-color: #FFF8E5;
          border-radius: 12rpx;

          .promise-icon {
            font-size: 32rpx;
            flex-shrink: 0;
          }

          .promise-content {
            flex: 1;

            .promise-title {
              font-size: 26rpx;
              font-weight: 500;
              color: var(--text-primary);
              display: block;
              margin-bottom: 4rpx;
            }

            .promise-desc {
              font-size: 24rpx;
              color: var(--text-secondary);
              line-height: 1.5;
              display: block;
            }
          }
        }
      }
    }

    .privacy-note {
      padding: 16rpx;
      background-color: #F5F5F5;
      border-radius: 8rpx;
      margin-top: 16rpx;

      text {
        display: block;
        font-size: 22rpx;
        color: var(--text-hint);
        line-height: 1.6;

        &:first-child {
          margin-bottom: 8rpx;
        }
      }
    }

    .contact-info {
      font-size: 24rpx;
      color: var(--color-primary);
      font-weight: 500;
      display: block;
      margin-top: 8rpx;
    }
  }

  .modal-footer {
    padding: 24rpx;
    border-top: 1rpx solid var(--border-color);

    .agree-btn {
      width: 100%;
      height: 88rpx;
      line-height: 88rpx;
      background: linear-gradient(135deg, #FF8A65, #FFAB91);
      color: #FFFFFF;
      font-size: 30rpx;
      font-weight: bold;
      border-radius: 44rpx;
      border: none;
    }
  }
}
</style>
