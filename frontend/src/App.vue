<template>
  <router-view />
</template>

<script setup>
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--p-font-family), sans-serif;
  background-color: var(--p-surface-ground);
  color: var(--p-text-color);
}

#app {
  min-height: 100vh;
}
</style>
