<template>
  <!-- rebuild the mobile entry as a focused login card that matches the provided inspiration while keeping the app's Chinese brand tone; mobile login page only; verify with npm run build:mobile:h5 -->
  <view class="auth-page auth-page--login">
    <view class="auth-shell auth-shell--login">
      <view class="auth-brand-mark">✦</view>

      <view class="auth-head">
        <text class="auth-title">欢迎回来！</text>
        <text class="auth-subtitle">开启您的健身之旅</text>
      </view>

      <view class="auth-form">
        <view class="auth-field">
          <text class="auth-label">手机号</text>
          <input v-model="phone" class="auth-input" type="number" maxlength="11" placeholder="请输入手机号" />
        </view>

        <view class="auth-field">
          <text class="auth-label">验证码</text>
          <input v-model="verifyCode" class="auth-input" type="number" maxlength="6" placeholder="请输入验证码" />
        </view>
      </view>

      <text v-if="errorMessage" class="auth-error">{{ errorMessage }}</text>

      <view class="auth-links auth-links--inline">
        <view class="auth-link-spacer"></view>
        <text class="auth-link" @click="handlePlaceholder('忘记密码')">忘记密码？</text>
      </view>

      <button class="auth-submit" :loading="submitting" @click="handleLogin">登录 →</button>

      <view class="auth-links auth-links--stack">
        <text class="auth-helper">还没有账号？</text>
        <text class="auth-link auth-link--strong" @click="goRegister">注册新账号</text>
      </view>

      <view class="auth-divider">
        <text>其他登录方式</text>
      </view>

      <view class="auth-social-row">
        <view class="auth-social-chip" @click="handlePlaceholder('微信快捷登录')">微信</view>
        <view class="auth-social-chip" @click="handlePlaceholder('Apple 登录')">iOS</view>
        <view class="auth-social-chip" @click="handlePlaceholder('生物识别')">指纹</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'

import { apiPost } from '../../api/client'
import { loadMobileSession, loadPrefilledPhone, saveMobileSession } from '../../lib/authSession'

const mobileAuthShell = inject('mobileAuthShell', null)
const phone = ref('')
const verifyCode = ref('')
const submitting = ref(false)
const errorMessage = ref('')

const normalizePhone = (value) => value.replace(/\s+/g, '')

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const goWorkoutHome = (session) => {
  if (mobileAuthShell?.completeLogin) {
    mobileAuthShell.completeLogin(session)
    return
  }

  if (typeof uni !== 'undefined' && typeof uni.reLaunch === 'function') {
    uni.reLaunch({ url: '/pages/workout/index' })
  }
}

const goRegister = () => {
  errorMessage.value = ''

  if (mobileAuthShell?.openAuthPage) {
    mobileAuthShell.openAuthPage('register')
    return
  }

  if (typeof uni !== 'undefined' && typeof uni.navigateTo === 'function') {
    uni.navigateTo({ url: '/pages/auth/register' })
  }
}

const handlePlaceholder = (label) => {
  showToast(`${label} 入口先保留占位`)
}

// keep mobile login on the existing gateway contract while using the preview shell when embedded in H5; mobile login submit behavior only; verify with npm run build:mobile:h5
const handleLogin = async () => {
  const normalizedPhone = normalizePhone(phone.value)
  const normalizedCode = verifyCode.value.trim()

  if (!/^1\d{10}$/.test(normalizedPhone)) {
    errorMessage.value = '请输入正确的 11 位手机号'
    return
  }

  if (normalizedCode.length < 4) {
    errorMessage.value = '请输入至少 4 位验证码'
    return
  }

  submitting.value = true
  errorMessage.value = ''

  try {
    const response = await apiPost('/auth/login', {
      phone: normalizedPhone,
      verify_code: normalizedCode,
    })

    if (!response?.access_token || !response?.user_id) {
      throw new Error('登录返回缺少会话信息')
    }

    const session = {
      accessToken: response.access_token,
      userId: response.user_id,
      phone: normalizedPhone,
    }

    saveMobileSession(session)
    showToast('登录成功')
    goWorkoutHome(session)
  } catch (error) {
    errorMessage.value = error?.message || error?.errMsg || '登录失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  const session = loadMobileSession()
  const embeddedPrefill = mobileAuthShell?.getPrefilledPhone?.() || ''
  phone.value = embeddedPrefill || loadPrefilledPhone()

  if (session?.userId) {
    goWorkoutHome(session)
  }
})
</script>

<style scoped lang="scss">
/* shape the mobile login page into a polished single-card flow close to the reference composition; mobile auth page presentation only; verify in H5 preview and mini-program login entry. */
.auth-page,
.auth-page *,
.auth-page *::before,
.auth-page *::after {
  box-sizing: border-box;
}

.auth-page {
  min-height: 100vh;
  padding: 28px 18px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.32), transparent 24%),
    radial-gradient(circle at bottom right, rgba(242, 17, 98, 0.14), transparent 28%),
    linear-gradient(180deg, #f2f4fa 0%, #f8f7fb 100%);
}

.auth-shell {
  width: 100%;
  max-width: 390px;
  margin: 0 auto;
  padding: 32px 22px 28px;
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 249, 253, 0.98));
  box-shadow:
    0 28px 60px rgba(29, 35, 55, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.auth-brand-mark,
.auth-submit,
.auth-social-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.auth-brand-mark {
  width: 58px;
  height: 58px;
  margin: 18px auto 26px;
  border-radius: 20px;
  color: #fff;
  font-size: 22px;
  font-weight: 800;
  background: linear-gradient(135deg, #f21162, #ff7a45);
  box-shadow: 0 18px 34px rgba(242, 17, 98, 0.22);
}

.auth-head {
  display: grid;
  gap: 8px;
  text-align: center;
}

.auth-title {
  font-size: 38px;
  font-weight: 800;
  color: #1c2233;
}

.auth-subtitle,
.auth-helper,
.auth-divider {
  color: #6e7485;
}

.auth-form {
  display: grid;
  gap: 16px;
  margin-top: 34px;
}

.auth-field {
  display: grid;
  gap: 10px;
}

.auth-label {
  font-size: 14px;
  font-weight: 700;
  color: #444d64;
}

.auth-input {
  width: 100%;
  min-height: 54px;
  padding: 0 18px;
  border: 0;
  border-radius: 18px;
  background: rgba(243, 245, 249, 0.96);
  color: #1c2233;
}

.auth-error {
  display: block;
  margin-top: 14px;
  color: #da185e;
  font-size: 13px;
}

.auth-links {
  display: flex;
}

.auth-links--inline {
  justify-content: space-between;
  margin-top: 12px;
}

.auth-link-spacer {
  width: 1px;
}

.auth-links--stack {
  margin-top: 24px;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.auth-link {
  color: #da185e;
  font-size: 14px;
  font-weight: 700;
}

.auth-link--strong {
  font-size: 16px;
}

.auth-submit {
  width: 100%;
  min-height: 56px;
  margin-top: 18px;
  border: 0;
  border-radius: 999px;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
  background: linear-gradient(135deg, #f21162, #ff6f79);
  box-shadow: 0 18px 32px rgba(242, 17, 98, 0.22);
}

.auth-divider {
  position: relative;
  margin-top: 28px;
  text-align: center;
  font-size: 12px;
}

.auth-divider::before,
.auth-divider::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 30%;
  height: 1px;
  background: rgba(110, 116, 133, 0.18);
}

.auth-divider::before {
  left: 0;
}

.auth-divider::after {
  right: 0;
}

.auth-social-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 22px;
}

.auth-social-chip {
  min-height: 48px;
  border-radius: 999px;
  color: #35405a;
  font-size: 14px;
  font-weight: 700;
  background: rgba(243, 245, 249, 0.96);
}
</style>
