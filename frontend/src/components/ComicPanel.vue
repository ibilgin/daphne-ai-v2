<template>
  <div class="comic-panel" :class="`layout-${layoutIndex}`">
    <div class="panel-image-wrapper">
      <img
        v-if="panel.image_bytes_b64"
        :src="`data:image/jpeg;base64,${panel.image_bytes_b64}`"
        :alt="panel.caption"
        class="panel-image"
      />
      <div v-else class="panel-placeholder">
        <i class="pi pi-image" style="font-size: 2rem; color: var(--p-surface-400)" />
      </div>
    </div>

    <div class="panel-narration">
      <p>{{ panel.narration }}</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  panel: {
    type: Object,
    required: true,
    // Shape: { image_bytes_b64, caption, narration, dialogue }
  },
  layoutIndex: {
    type: Number,
    default: 0,
  },
})
</script>

<style scoped>
.comic-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 3px solid #1a1a1a;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
  height: 100%;
}

.panel-image-wrapper {
  position: relative;
  flex: 1;
  overflow: hidden;
}

.panel-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.panel-placeholder {
  width: 100%;
  height: 100%;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--p-surface-100);
}

.panel-narration {
  padding: 6px 8px;
  background: #fffde7;
  border-top: 2px solid #1a1a1a;
  font-family: 'Comic Sans MS', 'Chalkboard SE', cursive;
  font-size: 0.75rem;
  line-height: 1.4;
  color: #1a1a1a;
  min-height: 36px;
}
</style>
