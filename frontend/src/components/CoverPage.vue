<template>
  <div class="cover-page">
    <div class="cover-border">
      <div class="cover-content">
        <div class="cover-stars">
          <span v-for="i in 5" :key="i" class="star">&#9733;</span>
        </div>

        <h1 class="cover-title">{{ comic.cover_title }}</h1>

        <div class="cover-divider" />

        <div class="cover-child-info">
          <p class="cover-label">A story for</p>
          <p class="cover-child-name">{{ comic.child_name }}</p>
        </div>

        <div class="cover-badge-wrapper">
          <Badge :value="formattedDate" severity="secondary" class="cover-date-badge" />
        </div>

        <div class="cover-decoration">
          <span class="deco-icon">&#127752;</span>
          <span class="deco-icon">&#9997;&#65039;</span>
          <span class="deco-icon">&#127752;</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Badge from 'primevue/badge'

const props = defineProps({
  comic: {
    type: Object,
    required: true,
    // Shape: { id, child_name, cover_title, created_at, pages }
  },
})

const formattedDate = computed(() => {
  if (!props.comic.created_at) return ''
  const d = new Date(props.comic.created_at)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
})
</script>

<style scoped>
.cover-page {
  width: 420px;
  height: 560px;
  background: linear-gradient(135deg, #1a237e 0%, #283593 50%, #3949ab 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.cover-border {
  width: 380px;
  height: 520px;
  border: 6px double #ffd600;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 20px rgba(255, 214, 0, 0.15);
}

.cover-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px;
  text-align: center;
}

.cover-stars {
  color: #ffd600;
  font-size: 1.4rem;
  letter-spacing: 6px;
}

.cover-title {
  font-family: 'Georgia', 'Times New Roman', serif;
  font-size: 1.8rem;
  font-weight: 700;
  color: #fff;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
  line-height: 1.2;
  max-width: 300px;
}

.cover-divider {
  width: 60%;
  height: 3px;
  background: linear-gradient(90deg, transparent, #ffd600, transparent);
}

.cover-label {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.7);
  text-transform: uppercase;
  letter-spacing: 2px;
  font-family: sans-serif;
}

.cover-child-name {
  font-size: 1.6rem;
  font-weight: 700;
  color: #ffd600;
  font-family: 'Georgia', serif;
  margin-top: 2px;
}

.cover-badge-wrapper {
  margin-top: 8px;
}

.cover-date-badge {
  background: rgba(255, 255, 255, 0.15) !important;
  color: rgba(255, 255, 255, 0.8) !important;
  font-size: 0.75rem;
}

.cover-decoration {
  font-size: 1.8rem;
  letter-spacing: 12px;
  margin-top: 8px;
}
</style>
