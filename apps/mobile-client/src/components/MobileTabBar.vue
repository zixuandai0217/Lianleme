<template>
  <!-- unify the three main mobile tabs into one light floating control for both H5 preview and runtime pages; bottom navigation only; verify with H5 smoke and mini-program preview -->
  <view class="mobile-tabbar">
    <view
      v-for="tab in mobileTabs"
      :key="tab.key"
      class="nav-item"
      :class="{ active: tab.key === currentTab }"
      :data-preview-tab="mode === 'preview' ? tab.key : null"
      @click="handleSelect(tab)"
      >
      <text class="nav-item-badge">{{ badgeMap[tab.key] }}</text>
      <view class="nav-icon-shell">
        <view class="nav-icon">
          <svg class="nav-icon-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              v-for="(path, index) in iconMap[tab.key]"
              :key="`${tab.key}-${index}`"
              :d="path"
              stroke="currentColor"
              stroke-width="1.9"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </view>
      </view>
      <text class="nav-label">{{ tab.label }}</text>
    </view>
  </view>
</template>

<script setup>
import { mobileTabs } from '../lib/tabbar'

const props = defineProps({
  currentTab: {
    type: String,
    required: true,
  },
  mode: {
    type: String,
    default: 'runtime',
  },
})

const emit = defineEmits(['change'])

// draw all three tab icons with inline SVG so H5 preview and mini-program share the same icon language without external assets; shared mobile bottom navigation only; verify by checking all three tabs render the same glyphs in preview and runtime
const iconMap = {
  workout: ['M6 10v4', 'M9 8v8', 'M9 12h6', 'M15 8v8', 'M18 10v4'],
  diet: ['M8 4v16', 'M8 8h3', 'M8 12h3', 'M8 16h3', 'M16 4v9', 'M16 13v7', 'M13.5 4v9'],
  progress: ['M5 7h14', 'M19 7v10', 'M5 17h14', 'M8 9l4 4 4-5'],
}

// add a compact command label above each tab so the APK nav reads more like a designed control bar than a generic tab strip; mobile tabbar labels only; verify with the mobile surface contract script and H5 preview.
const badgeMap = {
  workout: 'TRAIN',
  diet: 'MEAL',
  progress: 'REPORT',
}

const handleSelect = (tab) => {
  if (tab.key === props.currentTab) {
    return
  }

  if (props.mode === 'preview') {
    emit('change', tab.key)
    return
  }

  if (typeof uni !== 'undefined' && typeof uni.switchTab === 'function') {
    uni.switchTab({ url: tab.path })
  }
}
</script>

<style lang="scss">
.mobile-tabbar {
  position: fixed;
  left: 50%;
  bottom: calc(18px + env(safe-area-inset-bottom));
  transform: translateX(-50%);
  width: min(360px, calc(100vw - 28px));
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
  padding: 14px 12px 12px;
  border-radius: 32px;
  /* keep the computed tabbar backdrop in the bright range expected by the preview smoke while preserving the layered glass feel; mobile bottom nav surface only; verify with mobile_tabbar_preview_smoke.py. */
  background-color: rgba(255, 255, 255, 0.96);
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.97), rgba(250, 251, 255, 0.94));
  box-shadow:
    0 22px 50px rgba(28, 34, 51, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(18px);
  z-index: 28;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 2px 4px 4px;
  color: #9ca6bb;
  transition: transform 180ms ease, color 180ms ease;
}

.nav-item-badge {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 1.5px;
  color: rgba(108, 117, 138, 0.88);
}

.nav-icon-shell {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 76px;
  height: 68px;
  border-radius: 26px;
  transition:
    background 180ms ease,
    transform 180ms ease,
    box-shadow 180ms ease;
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 999px;
  color: currentColor;
}

.nav-icon-svg {
  width: 28px;
  height: 28px;
}

.nav-label {
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.4px;
}

.nav-item.active {
  color: #f86448;
  transform: translateY(-2px);
}

.nav-item.active .nav-item-badge {
  color: #f86448;
}

.nav-item.active .nav-icon-shell {
  background:
    radial-gradient(circle at top, rgba(255, 170, 104, 0.22), transparent 64%),
    linear-gradient(180deg, rgba(248, 100, 72, 0.14), rgba(248, 100, 72, 0.04));
}

.nav-item.active .nav-icon {
  background: rgba(248, 100, 72, 0.12);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.76),
    0 12px 20px rgba(248, 100, 72, 0.14);
}
</style>
