<template>
  <!-- shared right-side preview drawer; user and recipe detail previews stay visually consistent; verify with vite build -->
  <teleport to="body">
    <transition name="slide-in">
      <div v-if="open" class="drawer-overlay" @click.self="emit('close')">
        <aside class="side-drawer">
          <header class="side-drawer__head">
            <div>
              <h3>{{ title }}</h3>
              <p v-if="description">{{ description }}</p>
            </div>
            <button class="icon-button icon-button--soft" type="button" @click="emit('close')">
              <AppIcon name="close" :size="16" />
            </button>
          </header>
          <div class="side-drawer__body">
            <slot />
          </div>
        </aside>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue'

withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
  }>(),
  {
    description: '',
  },
)

const emit = defineEmits<{
  close: []
}>()
</script>
