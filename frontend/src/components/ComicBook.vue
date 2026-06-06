<template>
  <div class="comic-book-container">
    <!-- Cover page (hidden, referenced by StPageFlip) -->
    <div ref="coverEl" class="page page-cover" style="display:none">
      <CoverPage v-if="comic" :comic="comic" />
    </div>

    <!-- Story pages (hidden, referenced by StPageFlip) -->
    <div
      v-for="page in comic?.pages ?? []"
      :key="page.page_num"
      :ref="el => { if (el) pageEls[page.page_num] = el }"
      class="page"
      style="display:none"
    >
      <div class="page-inner" :class="`layout-${page.layout}`">
        <ComicPanel
          v-for="(panel, idx) in page.panels"
          :key="idx"
          :panel="panel"
          :layout-index="idx"
        />
      </div>
    </div>

    <!-- StPageFlip mount target -->
    <div ref="bookContainerEl" class="book-mount" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { PageFlip } from 'page-flip'
import CoverPage from './CoverPage.vue'
import ComicPanel from './ComicPanel.vue'

const props = defineProps({
  comic: {
    type: Object,
    default: null,
    // Shape: ComicSchema { id, child_name, cover_title, created_at, pages }
  },
})

const emit = defineEmits(['page-changed'])

const bookContainerEl = ref(null)
const coverEl = ref(null)
const pageEls = ref({})

let book = null

function collectPageElements() {
  const els = []
  if (coverEl.value) els.push(coverEl.value)
  const pages = props.comic?.pages ?? []
  for (const page of pages) {
    const el = pageEls.value[page.page_num]
    if (el) els.push(el)
  }
  return els
}

async function initBook() {
  if (!bookContainerEl.value || !props.comic) return

  // Destroy existing instance before creating a new one
  if (book) {
    book.destroy()
    book = null
  }

  book = new PageFlip(bookContainerEl.value, {
    width: 420,
    height: 560,
    showCover: true,
    flippingTime: 700,
    usePortrait: false,
    autoSize: true,
  })

  book.on('flip', (e) => {
    emit('page-changed', e.data)
  })

  await nextTick()
  const pageElements = collectPageElements()
  if (pageElements.length > 0) {
    book.loadFromHTML(pageElements)
  }
}

onMounted(async () => {
  await initBook()
})

watch(() => props.comic, async () => {
  await nextTick()
  await initBook()
})

onBeforeUnmount(() => {
  if (book) {
    book.destroy()
    book = null
  }
})

// Exposed methods for parent components
function next() {
  book?.flipNext()
}

function prev() {
  book?.flipPrev()
}

function goTo(n) {
  book?.flip(n)
}

defineExpose({ next, prev, goTo })
</script>

<style scoped>
.comic-book-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.book-mount {
  /* StPageFlip will inject its canvas/DOM here */
}

/* Layout grids for pages — applied to the hidden DOM nodes StPageFlip reads */
.page {
  width: 420px;
  height: 560px;
  background: #fff;
}

.page-inner {
  width: 100%;
  height: 100%;
  display: grid;
  gap: 4px;
  padding: 4px;
}

.layout-1 {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.layout-2 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

.layout-3 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.layout-3 > :first-child {
  grid-column: 1 / -1;
}

.layout-4 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}
</style>
