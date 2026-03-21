<template>
  <view class="page">
    <view class="card block profile-hero">
      <view>
        <text class="title">我的资料</text>
        <text class="sub">当前账号：{{ sessionPhoneLabel }}</text>
      </view>
      <view class="logout-chip" @click="handleLogout">退出登录</view>
    </view>
    <view class="card block">
      <text class="title">设置</text>
      <text class="sub">通知、隐私、主题</text>
    </view>
    <view class="card block">
      <text class="title">数据导出</text>
      <text class="sub">导出训练与饮食记录</text>
    </view>
    <view class="card block">
      <text class="title">账号管理</text>
      <text class="sub">注销与登录设备管理</text>
    </view>
  </view>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'

import { clearMobileSession, loadMobileSession, requireMobileAuth } from '../../lib/authSession'

const mobileAuthShell = inject('mobileAuthShell', null)
const session = ref(loadMobileSession())

const sessionPhoneLabel = computed(() => {
  return session.value?.phone || '未登录'
})

const showToast = (title) => {
  if (typeof uni !== 'undefined' && typeof uni.showToast === 'function') {
    uni.showToast({ title, icon: 'none' })
  }
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
/* Why: add px fallback for H5 to keep profile cards readable with current direct-entry runtime. */
/* Scope: profile page spacing/type styles only. */
/* Verify: profile page cards and text spacing are visibly styled on localhost:5173. */
.page { padding: 24px; padding: 24rpx; display: grid; gap: 16px; gap: 16rpx; }
.block { padding: 24px; padding: 24rpx; }
.title { font-size: 30px; font-size: 30rpx; font-weight: 700; display: block; }
.sub { margin-top: 8px; margin-top: 8rpx; color: #6e7485; display: block; }
.profile-hero { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.logout-chip { display: inline-flex; align-items: center; justify-content: center; min-height: 42px; padding: 0 18px; border-radius: 999px; color: #fff; font-size: 14px; font-weight: 700; background: linear-gradient(135deg, #f21162, #ff7a45); }
</style>
