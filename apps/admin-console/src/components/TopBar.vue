<template>
  <!-- top chrome for search, refresh and operator context; module pages share one interaction pattern; verify with vite build -->
  <header class="topbar">
    <label class="search-field">
      <AppIcon name="search" :size="16" />
      <input
        :value="search"
        type="text"
        :placeholder="placeholder"
        @input="emit('update:search', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <div class="topbar__actions">
      <button class="icon-button icon-button--soft" type="button" :disabled="busy" @click="emit('refresh')">
        <AppIcon name="refresh" :size="16" />
      </button>
      <button class="icon-button icon-button--soft icon-button--badge" type="button">
        <span v-if="noticeCount > 0" class="icon-button__badge">{{ noticeCount }}</span>
        <AppIcon name="bell" :size="16" />
      </button>
      <div class="topbar__profile">
        <div>
          <strong>{{ operator.displayName }}</strong>
          <p>{{ operator.roleLabel }}</p>
        </div>
        <div class="topbar__avatar">{{ operator.avatarLabel }}</div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import type { AdminSession } from '../types/admin'

import AppIcon from './AppIcon.vue'

withDefaults(
  defineProps<{
    search: string
    placeholder: string
    operator: AdminSession
    busy?: boolean
    noticeCount?: number
  }>(),
  {
    busy: false,
    noticeCount: 0,
  },
)

// render the topbar profile from authenticated operator data instead of fixed placeholder text; topbar identity display only; verify with npm --workspace apps/admin-console run build
const emit = defineEmits<{
  'update:search': [value: string]
  refresh: []
}>()
</script>
