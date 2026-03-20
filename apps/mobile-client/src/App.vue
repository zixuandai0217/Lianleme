<template>
  <view v-if="isBrowserPreview" class="preview-root">
    <view v-if="showPreviewBackChip" class="preview-back-chip" @click="closePreviewPage">
      返回
    </view>

    <view class="preview-page">
      <component :is="activePageComponent" />
    </view>

    <view v-if="!previewOverlayPage" class="preview-nav">
      <view
        v-for="tab in previewTabs"
        :key="tab.key"
        class="nav-item"
        :class="{ active: tab.key === activeTab }"
        :data-preview-tab="tab.key"
        @click="setActiveTab(tab.key)"
      >
        <view class="nav-icon">{{ tab.icon }}</view>
        <text class="nav-label">{{ tab.label }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, provide, ref } from 'vue'

import DietHome from './pages/diet/index.vue'
import ProfileHome from './pages/profile/index.vue'
import ProgressHome from './pages/progress/index.vue'
import PhotoCustomizePage from './pages/workout/photo-customize.vue'
import WorkoutHome from './pages/workout/index.vue'

// Why: keep H5 tab switching local to the browser preview shell so mini-program routes stay driven by `pages.json`; Scope: App root rendering and local preview navigation only; Verify: localhost:5173 opens on `练了么` and the diet smoke script can switch with `[data-preview-tab='diet']`.
const isBrowserPreview = typeof window !== 'undefined'
const activeTab = ref('workout')
const previewOverlayPage = ref('')
const previewTabs = [
  { key: 'workout', label: '练了么', icon: '✦' },
  { key: 'diet', label: '吃了么', icon: '◔' },
  { key: 'progress', label: '瘦了么', icon: '◎' },
]

const previewPages = {
  workout: WorkoutHome,
  diet: DietHome,
  progress: ProgressHome,
}

const overlayPages = {
  profile: ProfileHome,
  photoCustomize: PhotoCustomizePage,
}

const showPreviewBackChip = computed(() => {
  return Boolean(previewOverlayPage.value) && previewOverlayPage.value !== 'photoCustomize'
})

// keep H5 preview-only deep pages local to the root shell so tabs still demo quickly without changing business routing contracts; browser preview shell only; verify by clicking `个人中心` from the progress tab and checking `我的资料` appears.
const openPreviewPage = (pageKey) => {
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

provide('previewShell', {
  openPreviewPage,
  closePreviewPage,
})

const activePageComponent = computed(() => {
  if (previewOverlayPage.value) {
    return overlayPages[previewOverlayPage.value]
  }

  return previewPages[activeTab.value] || WorkoutHome
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

/* Why: anchor the shared H5 preview tab bar at the bottom of the viewport without changing page route behavior on non-browser targets; Scope: App root preview shell only; Verify: localhost:5173 keeps the tab bar visible while the workout and diet pages scroll underneath it. */
.preview-root {
  min-height: 100%;
}

.preview-page {
  padding-bottom: calc(118px + env(safe-area-inset-bottom));
}

.preview-back-chip {
  position: fixed;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #4f566b;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 16px 30px rgba(23, 28, 40, 0.14);
  z-index: 24;
}

.preview-nav {
  position: fixed;
  left: 50%;
  bottom: calc(18px + env(safe-area-inset-bottom));
  transform: translateX(-50%);
  width: min(358px, calc(100vw - 28px));
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow:
    0 22px 46px rgba(23, 28, 40, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
  z-index: 20;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 8px;
  border-radius: 20px;
  color: #8a90a5;
  transition:
    background 180ms ease,
    color 180ms ease,
    transform 180ms ease;
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 14px;
  background: #f7f8fc;
  font-size: 17px;
}

.nav-label {
  font-size: 12px;
  font-weight: 700;
}

.nav-item.active {
  background: linear-gradient(145deg, rgba(242, 17, 98, 0.12), rgba(255, 122, 69, 0.14));
  color: #f21162;
  transform: translateY(-1px);
}

.nav-item.active .nav-icon {
  background: linear-gradient(145deg, #f21162, #ff7a45);
  color: #ffffff;
  box-shadow: 0 14px 24px rgba(242, 17, 98, 0.2);
}
</style>
