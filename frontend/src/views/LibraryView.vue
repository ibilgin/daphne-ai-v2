<template>
  <div class="library-view">
    <div class="library-header">
      <h1 class="library-title">
        <i class="pi pi-book" /> Comic Library
      </h1>
      <Button
        label="Create New Comic"
        icon="pi pi-plus"
        @click="$router.push('/generate')"
        class="create-btn"
      />
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <ProgressSpinner />
      <p>Loading your comics...</p>
    </div>

    <!-- Empty state -->
    <div v-else-if="!library.length" class="empty-state">
      <div class="empty-illustration">
        <i class="pi pi-pencil" style="font-size: 5rem; color: var(--p-primary-300)" />
      </div>
      <h2>No comics yet!</h2>
      <p>Transform your child's drawing into a personalised comic book adventure.</p>
      <Button
        label="Create your first comic"
        icon="pi pi-sparkles"
        size="large"
        @click="$router.push('/generate')"
        class="mt-4"
      />
    </div>

    <!-- Comics grid -->
    <DataView v-else :value="library" layout="grid" class="comics-grid">
      <template #grid="slotProps">
        <div class="grid-items">
          <div v-for="comic in slotProps.items" :key="comic.id" class="grid-item">
            <Card class="comic-card">
              <template #header>
                <div class="card-cover">
                  <img
                    v-if="coverImage(comic)"
                    :src="coverImage(comic)"
                    :alt="comic.cover_title"
                    class="cover-img"
                  />
                  <div v-else class="cover-placeholder">
                    <i class="pi pi-book" style="font-size: 3rem; color: var(--p-surface-400)" />
                  </div>
                </div>
              </template>

              <template #title>{{ comic.cover_title }}</template>

              <template #subtitle>
                <span><i class="pi pi-user" /> {{ comic.child_name }}</span>
              </template>

              <template #content>
                <Badge :value="formatDate(comic.created_at)" severity="secondary" />
              </template>

              <template #footer>
                <Button
                  label="Read"
                  icon="pi pi-play"
                  class="read-btn"
                  @click="$router.push(`/read/${comic.id}`)"
                />
              </template>
            </Card>
          </div>
        </div>
      </template>
    </DataView>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useComicStore } from '../stores/comic.js'
import { storeToRefs } from 'pinia'
import DataView from 'primevue/dataview'
import Card from 'primevue/card'
import Badge from 'primevue/badge'
import Button from 'primevue/button'
import ProgressSpinner from 'primevue/progressspinner'

const store = useComicStore()
const { library } = storeToRefs(store)
const loading = ref(false)

function coverImage(comic) {
  const firstPanel = comic?.pages?.[0]?.panels?.[0]
  if (firstPanel?.image_bytes_b64) {
    return `data:image/png;base64,${firstPanel.image_bytes_b64}`
  }
  return null
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

onMounted(async () => {
  loading.value = true
  try {
    await store.fetchLibrary()
  } catch {
    // silently fail — empty state handles it
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.library-view {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
}

.library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2rem;
}

.library-title {
  font-size: 1.8rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 4rem;
  color: var(--p-text-muted-color);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 6rem 2rem;
  text-align: center;
}

.empty-illustration {
  margin-bottom: 1rem;
}

.empty-state h2 {
  font-size: 1.5rem;
  font-weight: 600;
}

.empty-state p {
  color: var(--p-text-muted-color);
  max-width: 400px;
}

.grid-items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1.5rem;
  padding: 1rem 0;
}

.comic-card {
  height: 100%;
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
}

.comic-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.card-cover {
  height: 180px;
  overflow: hidden;
  background: var(--p-surface-100);
  border-radius: var(--p-card-border-radius) var(--p-card-border-radius) 0 0;
}

.cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.read-btn {
  width: 100%;
}

.mt-4 {
  margin-top: 1rem;
}
</style>
