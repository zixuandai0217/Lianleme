<template>
  <!-- turn the simple placeholder profile into a beta-ready account hub with actions, safety copy, and structured personal context; mobile profile experience only; verify with build:h5 and node tests/e2e/mobile_surface_contract.mjs. -->
  <view class="page app-mobile-page">
    <view class="phone-shell app-mobile-shell app-mobile-shell--aurora">
      <view class="profile-hero-card app-mobile-signal-card">
        <view class="profile-hero-copy">
          <text class="app-mobile-section-kicker">PROFILE SYSTEM</text>
          <text class="profile-hero-title">我的资料与测试权限</text>
          <text class="profile-hero-subtitle">当前登录账号：{{ sessionAccountLabel }}</text>

          <view class="profile-chip-row">
            <view class="app-mobile-chip-btn">{{ accountTone }}</view>
            <view class="app-mobile-outline-btn" @click="handleAction('偏好设置')">偏好设置</view>
          </view>
        </view>

        <view class="profile-hero-avatar">
          <view class="profile-hero-ring"></view>
          <view class="profile-hero-core">{{ avatarLabel }}</view>
        </view>
      </view>

      <view class="app-mobile-metric-grid">
        <view class="app-mobile-metric-card">
          <strong>14</strong>
          <span>连续记录天数</span>
        </view>
        <view class="app-mobile-metric-card">
          <strong>Beta</strong>
          <span>当前测试阶段</span>
        </view>
      </view>

      <view class="app-mobile-inline-note">
        <strong>当前版本以演示和 APK 内测为主</strong>
        <span>账号、设备和导出能力先以清晰反馈为主，后续再接真实服务端逻辑。</span>
      </view>

      <view class="section-block">
        <view class="section-heading">
          <view>
            <text class="section-anchor">快捷操作</text>
            <text class="section-helper">围绕个人资料、隐私和设备同步的入口</text>
          </view>
        </view>

        <view class="profile-command-grid">
          <view
            v-for="item in commandCards"
            :key="item.title"
            class="profile-command-card app-mobile-card"
            @click="handleAction(item.title)"
          >
            <text class="profile-command-kicker">{{ item.kicker }}</text>
            <text class="profile-command-title">{{ item.title }}</text>
            <text class="profile-command-desc">{{ item.description }}</text>
          </view>
        </view>
      </view>

      <view class="profile-panel app-mobile-card">
        <view class="panel-head">
          <view>
            <text class="section-anchor">账号中心</text>
            <text class="section-helper">当前会话状态与基础身份信息</text>
          </view>
        </view>

        <view class="profile-detail-list">
          <view class="profile-detail-row">
            <text class="profile-detail-label">登录账号</text>
            <text class="profile-detail-value">{{ sessionAccountLabel }}</text>
          </view>
          <view class="profile-detail-row">
            <text class="profile-detail-label">测试身份</text>
            <text class="profile-detail-value">{{ accountTone }}</text>
          </view>
          <view class="profile-detail-row">
            <text class="profile-detail-label">可用能力</text>
            <text class="profile-detail-value">训练、饮食、周报、AI 搭子</text>
          </view>
        </view>
      </view>

      <view class="profile-panel app-mobile-card">
        <view class="panel-head">
          <view>
            <text class="section-anchor">安全与数据</text>
            <text class="section-helper">你后续最关心的就是资料、导出与设备同步</text>
          </view>
        </view>

        <view class="app-mobile-floating-note">
          <strong>数据导出</strong>
          <span>训练记录、饮食记录和体重趋势将在后续版本接入真实导出通道。</span>
        </view>
        <view class="app-mobile-floating-note">
          <strong>设备管理</strong>
          <span>当前 APK 内测版先保留单设备体验，后续接入真正的会话与设备策略。</span>
        </view>
      </view>

      <view class="profile-danger-card">
        <text class="profile-danger-title">退出当前账号</text>
        <text class="profile-danger-desc">退出后会返回登录页，本地测试会话会被清空。</text>
        <view class="profile-danger-button" @click="handleLogout">退出登录</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'

import { clearMobileSession, loadMobileSession, requireMobileAuth } from '../../lib/authSession'

const mobileAuthShell = inject('mobileAuthShell', null)
const session = ref(loadMobileSession())

const commandCards = [
  { kicker: 'PREFERENCES', title: '通知与偏好', description: '管理提醒频率、训练节奏与视觉偏好。' },
  { kicker: 'EXPORT', title: '数据导出', description: '导出训练、饮食和周报数据供复盘使用。' },
  { kicker: 'PRIVACY', title: '隐私与授权', description: '查看权限说明、照片用途和数据范围。' },
  { kicker: 'DEVICE', title: '登录设备', description: '管理当前设备会话与未来的设备同步能力。' },
]

const sessionAccountLabel = computed(() => {
  // show the simplified email-based identity in profile while keeping backward compatibility for older local sessions; mobile profile summary only; verify with the mobile auth flow smoke plus the mobile surface contract script.
  return session.value?.email || session.value?.phone || '未登录'
})

const avatarLabel = computed(() => {
  return (sessionAccountLabel.value || 'L').slice(0, 1).toUpperCase()
})

const accountTone = computed(() => {
  return session.value?.email ? '内测体验账号' : '访客演示账号'
})

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
}

const handleAction = (label) => {
  showToast(`${label} 将在后续版本接入真实功能`)
}

// keep logout reachable from the profile page in both the H5 preview shell and native page routing; mobile profile account actions only; verify by logging out from `我的资料` and returning to login.
const handleLogout = () => {
  clearMobileSession()
  session.value = null
  showToast('已退出登录')

  if (mobileAuthShell?.logout) {
    mobileAuthShell.logout()
    return
  }

  if (typeof uni !== 'undefined' && typeof uni.reLaunch === 'function') {
    uni.reLaunch({ url: '/pages/auth/login' })
  }
}

onMounted(() => {
  const activeSession = requireMobileAuth()
  if (!activeSession) {
    return
  }

  session.value = activeSession
})
</script>

<style scoped lang="scss">
/* align the profile page with the rest of the premium mobile shell while keeping every action in the existing demo-only behavior lane; profile layout and styling only; verify with build:h5 and node tests/e2e/mobile_surface_contract.mjs. */
/* keep the profile page box-sizing reset mp-weixin-safe by targeting supported uni elements instead of scoped universal selectors; profile layout only; verify with `npm --workspace apps/mobile-client run build:mp-weixin && node tests/e2e/mobile_mp_style_contract.mjs`. */
.page,
.page view,
.page text,
.page button,
.page input,
.page textarea,
.page image,
.page navigator,
.page scroll-view,
.page swiper,
.page swiper-item {
  box-sizing: border-box;
}

.page {
  min-height: 100vh;
  padding-top: 20px;
}

.phone-shell {
  display: grid;
  gap: 16px;
}

.profile-hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 22px;
}

.profile-hero-copy {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 12px;
  max-width: 220px;
}

.profile-hero-title {
  display: block;
  font-size: 30px;
  line-height: 1;
  font-weight: 900;
}

.profile-hero-subtitle {
  display: block;
  color: rgba(255, 255, 255, 0.74);
  line-height: 1.55;
}

.profile-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.profile-chip-row :deep(.app-mobile-chip-btn) {
  color: #1c2233;
}

.profile-chip-row :deep(.app-mobile-outline-btn) {
  border-color: rgba(255, 255, 255, 0.16);
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}

.profile-hero-avatar {
  position: relative;
  width: 112px;
  height: 112px;
  flex-shrink: 0;
}

.profile-hero-ring,
.profile-hero-core {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  border-radius: 32px;
}

.profile-hero-ring {
  border: 1px solid rgba(255, 255, 255, 0.16);
  transform: rotate(12deg);
}

.profile-hero-core {
  inset: 14px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(255, 236, 241, 0.78));
  color: #f21162;
  font-size: 34px;
  font-weight: 900;
}

.profile-command-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.profile-command-card,
.profile-panel,
.profile-danger-card {
  padding: 18px;
  border-radius: 26px;
}

.profile-command-card {
  display: grid;
  gap: 10px;
}

.profile-command-kicker {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 1.6px;
  color: #f0644d;
}

.profile-command-title {
  font-size: 18px;
  font-weight: 800;
  color: var(--mobile-ink);
}

.profile-command-desc {
  color: #6f7488;
  line-height: 1.55;
  font-size: 13px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.profile-detail-list {
  display: grid;
  gap: 12px;
}

.profile-detail-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid rgba(28, 34, 51, 0.08);
}

.profile-detail-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.profile-detail-label,
.profile-detail-value {
  display: block;
  max-width: 56%;
  line-height: 1.55;
}

.profile-detail-label {
  color: #70778d;
}

.profile-detail-value {
  text-align: right;
  font-weight: 700;
  color: var(--mobile-ink);
}

.profile-panel {
  display: grid;
  gap: 12px;
}

.profile-danger-card {
  display: grid;
  gap: 12px;
  background: linear-gradient(145deg, rgba(28, 34, 51, 0.98), rgba(53, 59, 84, 0.96));
  color: #fff;
  box-shadow: 0 24px 42px rgba(28, 34, 51, 0.24);
}

.profile-danger-title {
  font-size: 20px;
  font-weight: 800;
}

.profile-danger-desc {
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.55;
}

.profile-danger-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  border-radius: 999px;
  color: #1c2233;
  font-weight: 900;
  background: linear-gradient(135deg, #fff3f6, #ffd7c8);
}

@media (max-width: 420px) {
  .profile-hero-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .profile-hero-copy,
  .profile-detail-label,
  .profile-detail-value {
    max-width: none;
  }

  .profile-detail-row {
    flex-direction: column;
  }

  .profile-detail-value {
    text-align: left;
  }

  .profile-command-grid {
    grid-template-columns: 1fr;
  }
}
</style>
