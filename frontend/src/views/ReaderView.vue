<template>
  <div class="reader-view">
    <!-- Loading -->
    <div v-if="loading" class="reader-loading">
      <ProgressSpinner />
      <p>Loading your comic...</p>
    </div>

    <!-- Error -->
    <div v-else-if="loadError" class="reader-error">
      <i class="pi pi-exclamation-triangle" style="font-size: 3rem; color: var(--p-red-400)" />
      <p>{{ loadError }}</p>
      <Button label="Back to Library" @click="$router.push('/')" />
    </div>

    <!-- Reader -->
    <template v-else-if="comic">
      <!-- Toolbar -->
      <Toolbar class="reader-toolbar">
        <template #start>
          <Button
            icon="pi pi-arrow-left"
            text
            aria-label="Back to Library"
            @click="$router.push('/')"
          />
        </template>

        <template #center>
          <div class="page-indicator">
            <Button
              icon="pi pi-chevron-left"
              text
              aria-label="Previous page"
              :disabled="currentPage <= 0"
              @click="prevPage"
            />
            <span class="page-label">{{ currentPage + 1 }} / {{ totalPages }}</span>
            <Button
              icon="pi pi-chevron-right"
              text
              aria-label="Next page"
              :disabled="currentPage >= totalPages - 1"
              @click="nextPage"
            />
          </div>
        </template>

        <template #end>
          <Button
            :icon="isFullscreen ? 'pi pi-window-minimize' : 'pi pi-window-maximize'"
            text
            :aria-label="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
            @click="toggleFullscreen"
          />
        </template>
      </Toolbar>

      <!-- Main book area -->
      <div class="reader-main" ref="readerMainEl">
        <ComicBook
          ref="comicBookRef"
          :comic="comic"
          @page-changed="onPageChanged"
        />
      </div>

      <!-- Thumbnail strip -->
      <div class="thumbnail-strip">
        <div
          v-for="(page, idx) in allPages"
          :key="idx"
          class="thumbnail"
          :class="{ active: currentPage === idx }"
          @click="goToPage(idx)"
          :title="`Page ${idx + 1}`"
        >
          <img
            v-if="thumbImage(page)"
            :src="thumbImage(page)"
            :alt="`Page ${idx + 1}`"
            class="thumb-img"
          />
          <div v-else class="thumb-placeholder">
            <span>{{ idx + 1 }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Toolbar from 'primevue/toolbar'
import Button from 'primevue/button'
import ProgressSpinner from 'primevue/progressspinner'
import ComicBook from '../components/ComicBook.vue'
import { useComicStore } from '../stores/comic.js'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useComicStore()
const { currentComic: comic } = storeToRefs(store)

const comicBookRef = ref(null)
const readerMainEl = ref(null)
const loading = ref(false)
const loadError = ref(null)
const currentPage = ref(0)
const isFullscreen = ref(false)

// Cover + story pages as a flat list for the thumbnail strip
const allPages = computed(() => {
  if (!comic.value) return []
  // Index 0 = cover, then story pages
  return [{ _isCover: true }, ...(comic.value.pages ?? [])]
})

const totalPages = computed(() => allPages.value.length)

function thumbImage(page) {
  if (page._isCover) return null
  const firstPanel = page.panels?.[0]
  if (firstPanel?.image_bytes_b64) {
    return `data:image/png;base64,${firstPanel.image_bytes_b64}`
  }
  return null
}

function onPageChanged(pageNum) {
  currentPage.value = pageNum
}

function nextPage() {
  comicBookRef.value?.next()
}

function prevPage() {
  comicBookRef.value?.prev()
}

function goToPage(idx) {
  comicBookRef.value?.goTo(idx)
  currentPage.value = idx
}

async function toggleFullscreen() {
  if (!document.fullscreenElement) {
    await readerMainEl.value?.requestFullscreen()
    isFullscreen.value = true
  } else {
    await document.exitFullscreen()
    isFullscreen.value = false
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

onMounted(async () => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  loading.value = true
  try {
    await store.fetchComic(route.params.comicId)
  } catch (err) {
    loadError.value = err.message || 'Failed to load comic.'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  if (document.fullscreenElement) {
    document.exitFullscreen()
  }
})
</script>

<style scoped>
.reader-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #1a1a2e;
  overflow: hidden;
}

.reader-loading,
.reader-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 1rem;
  color: rgba(255, 255, 255, 0.8);
}

.reader-toolbar {
  flex-shrink: 0;
  background: rgba(0, 0, 0, 0.4) !important;
  border: none !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
}

.page-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.page-label {
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  min-width: 60px;
  text-align: center;
}

.reader-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 1rem;
}

/* Thumbnail strip */
.thumbnail-strip {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.5);
  overflow-x: auto;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.thumbnail {
  flex-shrink: 0;
  width: 52px;
  height: 70px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.2s;
}

.thumbnail.active {
  border-color: var(--p-primary-400);
}

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.8rem;
  font-weight: 600;
}
</style>
