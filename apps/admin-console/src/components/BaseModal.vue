<template>
  <!-- shared modal container; recipe and user CRUD reuse one polished overlay surface; verify with vite build -->
  <teleport to="body">
    <transition name="fade-up">
      <div v-if="open" class="overlay" @click.self="emit('close')">
        <section class="ui-modal" :class="[`ui-modal--${size}`]">
          <header class="ui-modal__head">
            <div>
              <h3>{{ title }}</h3>
              <p v-if="description">{{ description }}</p>
            </div>
            <button class="icon-button icon-button--soft" type="button" @click="emit('close')">
              <AppIcon name="close" :size="16" />
            </button>
          </header>
          <div class="ui-modal__body">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="ui-modal__foot">
            <slot name="footer" />
          </footer>
        </section>
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
    size?: 'md' | 'lg'
  }>(),
  {
    description: '',
    size: 'md',
  },
)

const emit = defineEmits<{
  close: []
}>()
</script>
