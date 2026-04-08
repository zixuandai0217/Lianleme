<template>
  <view v-if="isBrowserPreview" class="preview-root">
    <!-- add a lightweight ambient backdrop to the H5 preview shell so the mobile tabs sit inside the same atmosphere as the APK-facing UI; browser preview shell only; verify with build:h5 and visual preview. -->
    <view class="preview-ambient preview-ambient--north"></view>
    <view class="preview-ambient preview-ambient--east"></view>

    <template v-if="!isAuthenticated">
      <LoginPage v-if="activeAuthPage === 'login'" />
      <RegisterPage v-else />
    </template>

    <template v-else>
      <view v-if="showPreviewBackChip" class="preview-back-chip" @click="closePreviewPage">
        返回
      </view>

      <view class="preview-page">
        <WorkoutHome v-if="activePageKey === 'workout'" />
        <DietHome v-else-if="activePageKey === 'diet'" />
        <ProgressHome v-else-if="activePageKey === 'progress'" />
        <ProfileHome v-else-if="activePageKey === 'profile'" />
        <PhotoCustomizePage v-else-if="activePageKey === 'photoCustomize'" />
      </view>

      <MobileTabBar
        v-if="!previewOverlayPage"
        class="preview-nav"
        mode="preview"
        :current-tab="activeTab"
        @change="setActiveTab"
      />
    </template>
  </view>
</template>

<script setup>
import { computed, provide, ref } from 'vue'

import MobileTabBar from './components/MobileTabBar.vue'
import { clearMobileSession, loadMobileSession } from './lib/authSession'
import LoginPage from './pages/auth/login.vue'
import RegisterPage from './pages/auth/register.vue'
import { mobileTabs } from './lib/tabbar'
import DietHome from './pages/diet/index.vue'
import ProfileHome from './pages/profile/index.vue'
import ProgressHome from './pages/progress/index.vue'
import PhotoCustomizePage from './pages/workout/photo-customize.vue'
import WorkoutHome from './pages/workout/index.vue'

// keep H5 tab switching local to the browser preview shell so mini-program routes stay driven by `pages.json`; app root preview navigation only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
const isBrowserPreview = typeof window !== 'undefined'
const activeTab = ref('workout')
const previewOverlayPage = ref('')
const activeAuthPage = ref('login')
const mobileSession = ref(loadMobileSession())

const previewPages = {
  workout: WorkoutHome,
  diet: DietHome,
  progress: ProgressHome,
}

const overlayPages = {
  profile: ProfileHome,
  photoCustomize: PhotoCustomizePage,
}

const isAuthenticated = computed(() => {
  return Boolean(mobileSession.value?.userId)
})

const showPreviewBackChip = computed(() => {
  return isAuthenticated.value && Boolean(previewOverlayPage.value) && previewOverlayPage.value !== 'photoCustomize'
})

// keep H5 preview-only deep pages local to the root shell so tabs still demo quickly without changing business routing contracts; browser preview shell only; verify by clicking `个人中心` from the progress tab and checking `我的资料` appears.
const openPreviewPage = (pageKey) => {
  if (!isAuthenticated.value) {
    return
  }

  if (!overlayPages[pageKey]) {
    return
  }

  previewOverlayPage.value = pageKey

  if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }
}

const closePreviewPage = () => {
  previewOverlayPage.value = ''

  if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }
}

// keep the browser preview auth flow local to the root shell so login/register can switch without relying on uni routes; H5 auth gate only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
const openAuthPage = (pageKey) => {
  activeAuthPage.value = pageKey === 'register' ? 'register' : 'login'
}

const completeLogin = (session) => {
  mobileSession.value = session
  activeAuthPage.value = 'login'
  previewOverlayPage.value = ''
  activeTab.value = mobileTabs[0].key

  if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }
}

const logout = () => {
  clearMobileSession()
  mobileSession.value = null
  activeAuthPage.value = 'login'
  previewOverlayPage.value = ''

  if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }
}

provide('previewShell', {
  openPreviewPage,
  closePreviewPage,
})

// keep the preview auth shell minimal so login/register only need page switching plus session completion; H5 auth shell only; verify with `uv run --with playwright python tests/e2e/mobile_auth_email_flow_smoke.py`.
provide('mobileAuthShell', {
  openAuthPage,
  completeLogin,
  logout,
})

const activePageKey = computed(() => {
  if (previewOverlayPage.value) {
    return previewOverlayPage.value
  }

  return previewPages[activeTab.value] ? activeTab.value : mobileTabs[0].key
})

const setActiveTab = (tabKey) => {
  if (!previewPages[tabKey] || tabKey === activeTab.value) {
    return
  }

  previewOverlayPage.value = ''
  activeTab.value = tabKey

  if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }
}
</script>

<style lang="scss">
@import './uni.scss';

/* Why: provide H5 fallback root styling while preserving uni `page` global style behavior. */
/* Scope: browser container (`html/body/#app`) in browser runtime only. */
/* Verify: H5 first paint keeps expected background/font instead of browser defaults. */
html,
body,
#app {
  min-height: 100%;
  margin: 0;
  background: $bg;
  color: $ink;
  font-family: 'Source Han Sans CN', sans-serif;
}

page {
  background: $bg;
  color: $ink;
  font-family: 'Source Han Sans CN', sans-serif;
}

/* Why: anchor the shared H5 preview tab bar at the bottom of the viewport without changing page route behavior on non-browser targets; Scope: App root preview shell only; Verify: localhost:5273 keeps the tab bar visible while the workout and diet pages scroll underneath it. */
.preview-root {
  min-height: 100%;
  background:
    radial-gradient(circle at top left, rgba(255, 196, 158, 0.28), transparent 24%),
    radial-gradient(circle at top right, rgba(242, 17, 98, 0.14), transparent 20%),
    linear-gradient(180deg, #f4f5fb 0%, #f8f8fc 100%);
}

.preview-ambient {
  position: fixed;
  pointer-events: none;
  z-index: 0;
  filter: blur(8px);
}

.preview-ambient--north {
  inset: 20px auto auto 14px;
  width: 128px;
  height: 128px;
  border-radius: 38px;
  background: linear-gradient(145deg, rgba(255, 154, 84, 0.22), rgba(255, 255, 255, 0));
  transform: rotate(24deg);
}

.preview-ambient--east {
  inset: auto 6px 92px auto;
  width: 110px;
  height: 110px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(242, 17, 98, 0.18), rgba(242, 17, 98, 0));
}

.preview-page {
  position: relative;
  z-index: 1;
  padding-bottom: calc(152px + env(safe-area-inset-bottom));
}

.preview-back-chip {
  position: fixed;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  color: var(--mobile-ink);
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 18px 32px rgba(23, 28, 40, 0.14);
  backdrop-filter: blur(14px);
  z-index: 24;
}
</style>
