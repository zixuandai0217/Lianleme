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
  padding: 16px 12px 14px;
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow:
    0 20px 48px rgba(28, 34, 51, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
  z-index: 28;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 6px 4px 2px;
  color: #96a2ba;
}

.nav-icon-shell {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 74px;
  height: 74px;
  border-radius: 24px;
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
  letter-spacing: 0.3px;
}

.nav-item.active {
  color: #f86448;
}

.nav-item.active .nav-icon-shell {
  background: linear-gradient(180deg, rgba(248, 100, 72, 0.1), rgba(248, 100, 72, 0.04));
}

.nav-item.active .nav-icon {
  background: rgba(248, 100, 72, 0.12);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.76),
    0 12px 20px rgba(248, 100, 72, 0.14);
}
</style>
