<template>
  <view class="app-shell">
    <slot />
  </view>
</template>

<script setup>
</script>

<style lang="scss">
@import './uni.scss';

page {
  background: $bg;
  color: $ink;
  font-family: 'Source Han Sans CN', sans-serif;
}
</style>
