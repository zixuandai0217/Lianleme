<template>
  <!-- simplify auth to email/password only for the current demo flow; mobile register form only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`. -->
  <view class="auth-page auth-page--register">
    <view class="auth-shell auth-shell--register">
      <view class="auth-topbar">
        <view class="auth-back" @click="goLogin">←</view>
        <text class="auth-brand">练了么</text>
        <view class="auth-topbar-spacer"></view>
      </view>

      <view class="auth-register-head">
        <text class="auth-pill">FITNESS ECOSYSTEM</text>
        <text class="auth-title auth-title--left">创建账号</text>
        <text class="auth-subtitle auth-subtitle--left">使用邮箱和密码，快速进入练了么</text>
      </view>

      <view class="auth-form auth-form--register">
        <view class="auth-field">
          <text class="auth-label">邮箱</text>
          <input v-model="email" class="auth-input" type="text" placeholder="请输入邮箱" />
        </view>

        <view class="auth-field">
          <text class="auth-label">密码</text>
          <input v-model="password" class="auth-input" password placeholder="请输入密码" />
        </view>

        <view class="auth-field">
          <text class="auth-label">确认密码</text>
          <input v-model="confirmPassword" class="auth-input" password placeholder="请再次输入密码" />
        </view>
      </view>

      <text v-if="errorMessage" class="auth-error">{{ errorMessage }}</text>

      <button class="auth-submit" :loading="submitting" @click="handleRegister">注册并进入</button>

      <view class="auth-links auth-links--stack">
        <text class="auth-helper">已有账号？</text>
        <text class="auth-link auth-link--strong" @click="goLogin">去登录</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { inject, ref } from 'vue'

import { apiPost } from '../../api/client'
import { loadMobileSession, saveMobileSession } from '../../lib/authSession'

const mobileAuthShell = inject('mobileAuthShell', null)
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const errorMessage = ref('')

const normalizeEmail = (value) => value.trim().toLowerCase()
const isValidEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)

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

const goLogin = () => {
  errorMessage.value = ''

  if (mobileAuthShell?.openAuthPage) {
    mobileAuthShell.openAuthPage('login')
    return
  }

  if (typeof uni !== 'undefined' && typeof uni.redirectTo === 'function') {
    uni.redirectTo({ url: '/pages/auth/login' })
  }
}

// simplify demo registration to email/password so first-time users can enter the app without a second login step; mobile register submit only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
const handleRegister = async () => {
  const normalizedEmail = normalizeEmail(email.value)
  const normalizedPassword = password.value.trim()
  const normalizedConfirmPassword = confirmPassword.value.trim()

  if (!isValidEmail(normalizedEmail)) {
    errorMessage.value = '请输入有效邮箱地址'
    return
  }

  if (!normalizedPassword) {
    errorMessage.value = '请输入密码'
    return
  }

  if (normalizedPassword !== normalizedConfirmPassword) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  submitting.value = true
  errorMessage.value = ''

  try {
    const response = await apiPost('/auth/register', {
      email: normalizedEmail,
      password: normalizedPassword,
    })

    if (!response?.access_token || !response?.user_id) {
      throw new Error('注册返回缺少会话信息')
    }

    const session = {
      accessToken: response.access_token,
      userId: response.user_id,
      email: response.email || normalizedEmail,
    }

    saveMobileSession(session)
    showToast('注册成功')
    goWorkoutHome(session)
  } catch (error) {
    errorMessage.value = error?.message || error?.errMsg || '注册失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

const existingSession = loadMobileSession()
if (existingSession?.userId) {
  goWorkoutHome(existingSession)
}
</script>

<style scoped lang="scss">
/* keep the simplified registration page on the same centered card shell so the H5 preview stays phone-sized on desktop; mobile register page only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`. */
.auth-page,
.auth-page *,
.auth-page *::before,
.auth-page *::after {
  box-sizing: border-box;
}

// keep the auth wrapper in block formatting on H5 so the shared shell can stay centered instead of expanding across the viewport; mobile register shell only; verify with `node tests/e2e/mobile_auth_layout_smoke.mjs`.
.auth-page {
  display: block;
  min-height: 100vh;
  padding: 24px 18px;
  background:
    radial-gradient(circle at bottom left, rgba(242, 17, 98, 0.12), transparent 28%),
    radial-gradient(circle at top right, rgba(255, 183, 91, 0.18), transparent 24%),
    linear-gradient(180deg, #f7f3f1 0%, #f6f7fb 100%);
}

.auth-shell {
  display: block;
  width: 100%;
  max-width: 390px;
  margin: 0 auto;
  padding: 22px 20px 30px;
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(249, 250, 253, 0.98));
  box-shadow:
    0 28px 60px rgba(29, 35, 55, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.auth-topbar,
.auth-links {
  display: flex;
  align-items: center;
}

.auth-topbar {
  justify-content: space-between;
}

.auth-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: rgba(243, 245, 249, 0.96);
  color: #35405a;
  font-size: 18px;
  font-weight: 700;
}

.auth-topbar-spacer {
  width: 32px;
}

.auth-brand {
  color: #f21162;
  font-size: 28px;
  font-style: italic;
  font-weight: 800;
}

.auth-register-head {
  display: grid;
  gap: 10px;
  margin-top: 22px;
}

.auth-pill {
  display: inline-flex;
  width: fit-content;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(242, 17, 98, 0.1);
  color: #f21162;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
}

.auth-title {
  font-size: 38px;
  font-weight: 800;
  color: #1c2233;
}

.auth-title--left,
.auth-subtitle--left {
  text-align: left;
}

.auth-subtitle,
.auth-helper {
  color: #6e7485;
}

.auth-form {
  display: grid;
  gap: 16px;
  margin-top: 28px;
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
  min-height: 52px;
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

.auth-submit {
  width: 100%;
  min-height: 56px;
  margin-top: 22px;
  border: 0;
  border-radius: 999px;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
  background: linear-gradient(135deg, #f21162, #ff6f79);
  box-shadow: 0 18px 32px rgba(242, 17, 98, 0.22);
}

.auth-links--stack {
  margin-top: 24px;
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
</style>
