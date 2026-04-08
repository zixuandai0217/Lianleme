<template>
  <!-- simplify auth to email/password only for the current demo flow; mobile login form only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`. -->
  <view class="auth-page auth-page--login" :class="{ 'auth-page--browser': isBrowserPreview, 'auth-page--immersive': !isBrowserPreview }">
    <view class="auth-shell auth-shell--login" :class="{ 'auth-shell--browser': isBrowserPreview, 'auth-shell--immersive': !isBrowserPreview }">
      <view class="auth-brand-mark">✦</view>

      <view class="auth-head">
        <text class="auth-title">欢迎回来</text>
        <text class="auth-subtitle">输入邮箱和密码，继续您的训练计划</text>
      </view>

      <view class="auth-form">
        <view class="auth-field">
          <text class="auth-label">邮箱</text>
          <input v-model="email" class="auth-input" type="text" placeholder="请输入邮箱" />
        </view>

        <view class="auth-field">
          <text class="auth-label">密码</text>
          <input v-model="password" class="auth-input" password placeholder="请输入密码" />
        </view>
      </view>

      <text v-if="errorMessage" class="auth-error">{{ errorMessage }}</text>

      <button class="auth-submit" :loading="submitting" @click="handleLogin">登录</button>

      <view class="auth-links auth-links--stack">
        <text class="auth-helper">还没有账号？</text>
        <text class="auth-link auth-link--strong" @click="goRegister">注册新账号</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'

import { apiPost } from '../../api/client'
import { loadMobileSession, saveMobileSession } from '../../lib/authSession'

const mobileAuthShell = inject('mobileAuthShell', null)
const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const isBrowserPreview = typeof window !== 'undefined'

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

  // harden the post-login tab entry for mini-program runtime by falling back to reLaunch when switchTab fails, instead of leaving the user on the auth screen after a successful toast; auth success navigation only; verify with `node tests/e2e/mobile_mp_auth_contract.mjs` and wx devtools login.
  if (typeof uni !== 'undefined' && typeof uni.switchTab === 'function') {
    uni.switchTab({
      url: '/pages/workout/index',
      fail: () => {
        if (typeof uni.reLaunch === 'function') {
          uni.reLaunch({ url: '/pages/workout/index' })
        }
      },
    })
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

// simplify demo login to email/password so the app preview can enter the authenticated shell without extra auth steps; mobile login submit only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
const handleLogin = async () => {
  const normalizedEmail = normalizeEmail(email.value)
  const normalizedPassword = password.value.trim()

  if (!isValidEmail(normalizedEmail)) {
    errorMessage.value = '请输入有效邮箱地址'
    return
  }

  if (!normalizedPassword) {
    errorMessage.value = '请输入密码'
    return
  }

  submitting.value = true
  errorMessage.value = ''

  try {
    const response = await apiPost('/auth/login', {
      email: normalizedEmail,
      password: normalizedPassword,
    })

    if (!response?.access_token || !response?.user_id) {
      throw new Error('登录返回缺少会话信息')
    }

    const session = {
      accessToken: response.access_token,
      userId: response.user_id,
      email: response.email || normalizedEmail,
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

  if (session?.userId) {
    goWorkoutHome(session)
  }
})
</script>

<style scoped lang="scss">
/* keep the simplified login page on the same centered card shell so the H5 preview stays phone-sized on desktop; mobile login page only; verify with `node tests/e2e/mobile_auth_layout_smoke.mjs`. */
/* keep the auth-page box-sizing reset mp-weixin-safe by targeting supported uni elements instead of scoped universal selectors; login page layout only; verify with `npm --workspace apps/mobile-client run build:mp-weixin && node tests/e2e/mobile_mp_style_contract.mjs`. */
.auth-page,
.auth-page view,
.auth-page text,
.auth-page button,
.auth-page input,
.auth-page textarea,
.auth-page image,
.auth-page navigator,
.auth-page scroll-view,
.auth-page swiper,
.auth-page swiper-item {
  box-sizing: border-box;
}

// keep the browser preview on a centered card while allowing mini-program runtime to switch to a full-bleed shell; login page layout only; verify with `node tests/e2e/mobile_auth_layout_smoke.mjs` and `node tests/e2e/mobile_mp_auth_contract.mjs`.
.auth-page--browser {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: calc(28px + env(safe-area-inset-top)) 18px calc(32px + env(safe-area-inset-bottom));
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.32), transparent 24%),
    radial-gradient(circle at bottom right, rgba(242, 17, 98, 0.14), transparent 28%),
    linear-gradient(180deg, #f2f4fa 0%, #f8f7fb 100%);
}

.auth-page--immersive {
  min-height: 100vh;
  padding: calc(20px + env(safe-area-inset-top)) 0 calc(24px + env(safe-area-inset-bottom));
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.32), transparent 24%),
    radial-gradient(circle at bottom right, rgba(242, 17, 98, 0.14), transparent 28%),
    linear-gradient(180deg, #f2f4fa 0%, #f8f7fb 100%);
}

.auth-shell--browser {
  display: block;
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

.auth-shell--immersive {
  display: grid;
  align-content: center;
  width: 100%;
  min-height: calc(100vh - env(safe-area-inset-top) - env(safe-area-inset-bottom));
  padding: 26px 28px 20px;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.auth-brand-mark,
.auth-submit {
  align-items: center;
  justify-content: center;
}

// keep the login brand mark block-level so auto margins can center it inside the auth shell; login hero mark only; verify with `node tests/e2e/mobile_auth_layout_smoke.mjs`.
.auth-brand-mark {
  display: flex;
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
.auth-helper {
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
  display: flex;
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
</style>
