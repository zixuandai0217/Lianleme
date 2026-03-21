<template>
  <!-- provide a matching registration flow so the mobile auth experience feels complete without adding new backend contracts; mobile registration page only; verify with npm run build:mobile:h5 -->
  <view class="auth-page auth-page--register">
    <view class="auth-shell auth-shell--register">
      <view class="auth-topbar">
        <view class="auth-back" @click="goLogin">←</view>
        <text class="auth-brand">练了么</text>
        <view class="auth-topbar-spacer"></view>
      </view>

      <view class="auth-register-head">
        <text class="auth-pill">FITNESS ECOSYSTEM</text>
        <text class="auth-title auth-title--left">加入练了么</text>
        <text class="auth-subtitle auth-subtitle--left">创建账号，开启更稳定的训练节奏</text>
      </view>

      <view class="auth-form auth-form--register">
        <view class="auth-field">
          <text class="auth-label">手机号</text>
          <input v-model="phone" class="auth-input" type="number" maxlength="11" placeholder="请输入手机号" />
        </view>

        <view class="auth-field auth-field--inline">
          <view class="auth-field-grow">
            <text class="auth-label">验证码</text>
            <input v-model="verifyCode" class="auth-input" type="number" maxlength="6" placeholder="请输入验证码" />
          </view>
          <view class="auth-mini-btn" @click="handlePlaceholder('发送验证码')">发送验证码</view>
        </view>

        <view class="auth-field">
          <text class="auth-label">设置密码</text>
          <input v-model="password" class="auth-input" password placeholder="至少 8 位字符" />
        </view>

        <view class="auth-field">
          <text class="auth-label">确认密码</text>
          <input v-model="confirmPassword" class="auth-input" password placeholder="再次输入密码" />
        </view>
      </view>

      <view class="auth-agreement" @click="agreed = !agreed">
        <view class="auth-check" :class="{ 'auth-check--active': agreed }">{{ agreed ? '✓' : '' }}</view>
        <text class="auth-agreement-text">我已阅读并同意</text>
        <text class="auth-link" @click.stop="handlePlaceholder('用户协议')">用户协议</text>
        <text class="auth-agreement-text">与</text>
        <text class="auth-link" @click.stop="handlePlaceholder('隐私政策')">隐私政策</text>
      </view>

      <text v-if="errorMessage" class="auth-error">{{ errorMessage }}</text>

      <button class="auth-submit" @click="handleRegister">立即注册</button>

      <view class="auth-links auth-links--stack">
        <text class="auth-helper">已有账号？</text>
        <text class="auth-link auth-link--strong" @click="goLogin">去登录</text>
      </view>

      <view class="auth-divider">
        <text>快捷登录</text>
      </view>

      <view class="auth-social-row auth-social-row--two">
        <view class="auth-social-chip" @click="handlePlaceholder('微信快捷登录')">微信</view>
        <view class="auth-social-chip" @click="handlePlaceholder('QQ 快捷登录')">QQ</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { inject, ref } from 'vue'

import { loadMobileSession, savePrefilledPhone } from '../../lib/authSession'

const mobileAuthShell = inject('mobileAuthShell', null)
const phone = ref('')
const verifyCode = ref('')
const password = ref('')
const confirmPassword = ref('')
const agreed = ref(false)
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

const handlePlaceholder = (label) => {
  showToast(`${label} 入口先保留占位`)
}

// keep registration local-only for now while preserving realistic field validation and back-to-login prefill behavior; mobile registration submit only; verify with npm run build:mobile:h5
const handleRegister = () => {
  const normalizedPhone = normalizePhone(phone.value)

  if (!/^1\d{10}$/.test(normalizedPhone)) {
    errorMessage.value = '请输入正确的 11 位手机号'
    return
  }

  if (verifyCode.value.trim().length < 4) {
    errorMessage.value = '请输入至少 4 位验证码'
    return
  }

  if (password.value.trim().length < 8) {
    errorMessage.value = '密码至少需要 8 位字符'
    return
  }

  if (password.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  if (!agreed.value) {
    errorMessage.value = '请先同意用户协议与隐私政策'
    return
  }

  savePrefilledPhone(normalizedPhone)

  if (mobileAuthShell?.setPrefilledPhone) {
    mobileAuthShell.setPrefilledPhone(normalizedPhone)
  }

  showToast('注册成功，请登录')
  goLogin()
}

const existingSession = loadMobileSession()
if (existingSession?.userId) {
  goWorkoutHome(existingSession)
}
</script>

<style scoped lang="scss">
/* match the registration page to the login language while fitting the longer field stack and agreement row; mobile register page styling only; verify in H5 preview and mini-program login flow. */
.auth-page,
.auth-page *,
.auth-page *::before,
.auth-page *::after {
  box-sizing: border-box;
}

.auth-page {
  min-height: 100vh;
  padding: 24px 18px;
  background:
    radial-gradient(circle at bottom left, rgba(242, 17, 98, 0.12), transparent 28%),
    radial-gradient(circle at top right, rgba(255, 183, 91, 0.18), transparent 24%),
    linear-gradient(180deg, #f7f3f1 0%, #f6f7fb 100%);
}

.auth-shell {
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
.auth-field--inline,
.auth-agreement,
.auth-links,
.auth-social-chip {
  display: flex;
  align-items: center;
}

.auth-topbar,
.auth-field--inline {
  justify-content: space-between;
}

.auth-back,
.auth-mini-btn,
.auth-check,
.auth-social-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.auth-back,
.auth-topbar-spacer {
  width: 32px;
}

.auth-back {
  height: 32px;
  border-radius: 999px;
  background: rgba(243, 245, 249, 0.96);
  color: #35405a;
  font-size: 18px;
  font-weight: 700;
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
.auth-helper,
.auth-agreement-text,
.auth-divider {
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

.auth-field-grow {
  flex: 1;
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

.auth-mini-btn {
  min-width: 102px;
  height: 52px;
  margin-top: 26px;
  border-radius: 999px;
  color: #f21162;
  font-size: 13px;
  font-weight: 700;
  background: rgba(243, 245, 249, 0.96);
}

.auth-agreement {
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 18px;
}

.auth-check {
  width: 22px;
  height: 22px;
  border-radius: 8px;
  border: 1px solid rgba(110, 116, 133, 0.32);
  color: #fff;
}

.auth-check--active {
  border-color: #f21162;
  background: #f21162;
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
  gap: 12px;
  margin-top: 22px;
}

.auth-social-row--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
