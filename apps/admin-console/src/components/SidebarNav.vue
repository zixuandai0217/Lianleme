<template>
  <!-- persistent console navigation; four core modules and operator identity live in one shell; verify with vite build -->
  <aside class="sidebar">
    <div class="brand-card">
      <div class="brand-card__logo">
        <AppIcon name="sparkles" :size="18" />
      </div>
      <div>
        <strong>练了么后台</strong>
        <p>健身 SaaS</p>
      </div>
    </div>

    <!-- keep the sidebar grounded in the demo scope so the polished console still tells operators what environment they are in; admin sidebar context only; verify with npm --workspace apps/admin-console run build. -->
    <div class="sidebar__badge">
      <span>运营指挥台</span>
      <strong>前后台联动演示环境</strong>
    </div>

    <nav class="sidebar__nav">
      <button
        v-for="module in modules"
        :key="module.key"
        class="nav-item"
        :class="{ 'nav-item--active': module.key === activeModule }"
        type="button"
        @click="emit('navigate', module.key)"
      >
        <AppIcon :name="module.icon" :size="18" />
        <span>{{ module.label }}</span>
      </button>
    </nav>

    <div class="sidebar__footer">
      <div class="operator-card">
        <div class="operator-card__avatar">{{ operator.avatarLabel }}</div>
        <div>
          <strong>{{ operator.displayName }}</strong>
          <p>{{ operator.roleLabel }}</p>
        </div>
      </div>
      <button class="logout-button" type="button" @click="emit('logout')">
        <AppIcon name="logout" :size="16" />
        退出登录
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import type { AdminModuleKey } from '../types/admin'
import type { AdminSession } from '../types/admin'
import AppIcon from './AppIcon.vue'

defineProps<{
  modules: Array<{
    key: AdminModuleKey
    label: string
    icon: string
  }>
  activeModule: AdminModuleKey
  operator: AdminSession
}>()

// render the sidebar identity from live auth session instead of fixed demo copy; sidebar operator card and logout action only; verify with npm --workspace apps/admin-console run build
const emit = defineEmits<{
  navigate: [module: AdminModuleKey]
  logout: []
}>()
</script>
