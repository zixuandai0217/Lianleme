<template>
  <WorkoutHome />
</template>

<script setup>
import WorkoutHome from './pages/workout/index.vue'

// Why: render an explicit visible root page so H5 direct entry does not end up with an empty shell.
// Scope: mobile-client root component rendering path in H5 browser runtime.
// Verify: opening `http://localhost:5173/` shows workout home content immediately.
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
</style>
