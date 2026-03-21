<template>
  <!-- central icon renderer; keeps sidebar and action glyphs consistent without extra dependencies; verify with vite build -->
  <svg
    class="app-icon"
    :viewBox="icon.viewBox"
    :width="size"
    :height="size"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <path
      v-for="(path, index) in icon.paths"
      :key="`${name}-${index}`"
      :d="path"
      stroke="currentColor"
      stroke-linecap="round"
      stroke-linejoin="round"
      :stroke-width="strokeWidth"
    />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface IconDefinition {
  viewBox: string
  paths: string[]
}

const props = withDefaults(
  defineProps<{
    name: string
    size?: number
    strokeWidth?: number
  }>(),
  {
    size: 20,
    strokeWidth: 1.85,
  },
)

const icons: Record<string, IconDefinition> = {
  dashboard: { viewBox: '0 0 24 24', paths: ['M4 4h6v6H4z', 'M14 4h6v10h-6z', 'M4 14h6v6H4z', 'M14 18h6v2h-6z'] },
  recipes: { viewBox: '0 0 24 24', paths: ['M6 5.5A2.5 2.5 0 0 1 8.5 3H19v18H8.5A2.5 2.5 0 0 0 6 23V5.5Z', 'M6 5.5A2.5 2.5 0 0 1 8.5 3H19', 'M10 8h5', 'M10 12h5', 'M10 16h3'] },
  users: { viewBox: '0 0 24 24', paths: ['M16 21v-1.5A3.5 3.5 0 0 0 12.5 16h-5A3.5 3.5 0 0 0 4 19.5V21', 'M10 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M20 21v-1.5A3.5 3.5 0 0 0 17.5 16.15', 'M15.5 5.15a3 3 0 0 1 0 5.7'] },
  settings: { viewBox: '0 0 24 24', paths: ['M12 3v3', 'M12 18v3', 'M4.2 6.2l2.1 2.1', 'M17.7 17.7l2.1 2.1', 'M3 12h3', 'M18 12h3', 'M4.2 17.8l2.1-2.1', 'M17.7 6.3l2.1-2.1', 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z'] },
  bell: { viewBox: '0 0 24 24', paths: ['M6.5 9.5a5.5 5.5 0 1 1 11 0c0 5 2 6.5 2 6.5h-15s2-1.5 2-6.5', 'M10 19a2 2 0 0 0 4 0'] },
  search: { viewBox: '0 0 24 24', paths: ['M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z', 'M20 20l-3.6-3.6'] },
  plus: { viewBox: '0 0 24 24', paths: ['M12 5v14', 'M5 12h14'] },
  refresh: { viewBox: '0 0 24 24', paths: ['M20 5v5h-5', 'M4 19v-5h5', 'M7 17a7 7 0 0 0 11.5-2', 'M17 7A7 7 0 0 0 5.5 9'] },
  eye: { viewBox: '0 0 24 24', paths: ['M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z'] },
  edit: { viewBox: '0 0 24 24', paths: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 1 1 3 3L8 18l-4 1 1-4 11.5-11.5Z'] },
  trash: { viewBox: '0 0 24 24', paths: ['M4 7h16', 'M10 11v6', 'M14 11v6', 'M6 7l1 12h10l1-12', 'M9 7V4h6v3'] },
  chevronDown: { viewBox: '0 0 24 24', paths: ['m6 9 6 6 6-6'] },
  chevronLeft: { viewBox: '0 0 24 24', paths: ['m14 6-6 6 6 6'] },
  chevronRight: { viewBox: '0 0 24 24', paths: ['m10 6 6 6-6 6'] },
  close: { viewBox: '0 0 24 24', paths: ['M6 6l12 12', 'M18 6 6 18'] },
  fire: { viewBox: '0 0 24 24', paths: ['M12 3s4 3 4 8a4 4 0 1 1-8 0c0-2 1-4 2.5-5.5', 'M12 13c1.5 1 2 2.1 2 3a2 2 0 1 1-4 0c0-.9.4-1.9 2-3Z'] },
  pulse: { viewBox: '0 0 24 24', paths: ['M3 12h4l2-4 4 8 2-4h6'] },
  sparkles: { viewBox: '0 0 24 24', paths: ['M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3Z', 'M19 15l.75 2.25L22 18l-2.25.75L19 21l-.75-2.25L16 18l2.25-.75L19 15Z', 'M5 14l.75 2.25L8 17l-2.25.75L5 20l-.75-2.25L2 17l2.25-.75L5 14Z'] },
  palette: { viewBox: '0 0 24 24', paths: ['M12 3a9 9 0 0 0 0 18h1.2a2.3 2.3 0 0 0 0-4.6H12a1.7 1.7 0 0 1 0-3.4h1.5A4.5 4.5 0 0 0 18 8.5 5.5 5.5 0 0 0 12 3Z', 'M7.5 10.5h.01', 'M8.5 7.5h.01', 'M12 6.5h.01', 'M15.5 8.5h.01'] },
  upload: { viewBox: '0 0 24 24', paths: ['M12 16V5', 'M8 9l4-4 4 4', 'M4 19h16'] },
  dumbbell: { viewBox: '0 0 24 24', paths: ['M4 10v4', 'M7 8v8', 'M10 11h4', 'M17 8v8', 'M20 10v4'] },
  save: { viewBox: '0 0 24 24', paths: ['M5 4h11l3 3v13H5V4Z', 'M9 4v5h6V4', 'M9 20v-6h6v6'] },
  reset: { viewBox: '0 0 24 24', paths: ['M4 4v6h6', 'M20 20v-6h-6', 'M8 20a8 8 0 0 1-4-10', 'M16 4a8 8 0 0 1 4 10'] },
  logout: { viewBox: '0 0 24 24', paths: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'M16 17l5-5-5-5', 'M21 12H9'] },
  chart: { viewBox: '0 0 24 24', paths: ['M4 19V5', 'M4 19h16', 'M8 15l3-3 3 2 5-6'] },
}

const icon = computed(() => icons[props.name] ?? icons.sparkles)
</script>
