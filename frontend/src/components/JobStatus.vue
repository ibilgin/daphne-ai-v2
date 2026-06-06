<template>
  <div class="job-status">
    <!-- Error state -->
    <div v-if="error" class="status-error">
      <div class="error-icon">
        <i class="pi pi-times-circle" style="font-size: 3rem; color: var(--p-red-500)" />
      </div>
      <p class="error-message">{{ error }}</p>
      <Button label="Try Again" icon="pi pi-refresh" @click="retry" class="mt-3" />
    </div>

    <!-- Progress state -->
    <div v-else class="status-progress">
      <div class="stage-icon">
        <i :class="stageIcon" style="font-size: 2.5rem" />
      </div>

      <h3 class="stage-label">{{ stageLabel }}</h3>

      <ProgressBar :value="progressPct" class="progress-bar" />

      <p class="progress-pct-text">{{ progressPct }}%</p>

      <p class="status-message">{{ statusMessage }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import ProgressBar from 'primevue/progressbar'
import Button from 'primevue/button'
import { useComicStore } from '../stores/comic.js'

const props = defineProps({
  jobId: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['complete', 'failed'])

const store = useComicStore()
const error = ref(null)
let pollPromise = null

const progressPct = computed(() => store.activeJob?.progress_pct ?? 0)
const currentStage = computed(() => store.activeJob?.stage ?? 'queued')

const stageIcon = computed(() => {
  const icons = {
    queued: 'pi pi-clock',
    captioning: 'pi pi-eye',
    storytelling: 'pi pi-pen-to-square',
    rendering: 'pi pi-image',
    safety_check: 'pi pi-shield',
    processing: 'pi pi-cog pi-spin',
    complete: 'pi pi-check-circle',
  }
  return icons[currentStage.value] ?? 'pi pi-cog pi-spin'
})

const stageLabel = computed(() => {
  const labels = {
    queued: 'Waiting in queue...',
    captioning: 'Understanding your drawing',
    storytelling: 'Crafting your story',
    rendering: 'Drawing comic panels',
    safety_check: 'Reviewing for safety',
    processing: 'Processing...',
    complete: 'All done!',
  }
  return labels[currentStage.value] ?? currentStage.value
})

const statusMessage = computed(() => {
  const messages = {
    queued: 'Your comic is lined up and ready to go!',
    captioning: 'The AI is looking at your sketch to understand what you drew...',
    storytelling: 'Turning your drawing into a personalised adventure story...',
    rendering: 'Creating beautiful comic panels from your story...',
    safety_check: 'Making sure everything is perfect for young readers...',
    processing: 'Working on your comic, hang tight!',
    complete: 'Your comic is ready!',
  }
  return messages[currentStage.value] ?? 'Working on your comic...'
})

async function startPolling() {
  error.value = null
  try {
    const job = await store.pollJob(props.jobId)
    emit('complete', job.result_id)
  } catch (err) {
    error.value = err.message || 'Something went wrong generating your comic.'
    emit('failed', error.value)
  }
}

function retry() {
  startPolling()
}

onMounted(() => {
  startPolling()
})
</script>

<style scoped>
.job-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  min-height: 280px;
}

.status-progress,
.status-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  width: 100%;
  max-width: 480px;
  text-align: center;
}

.stage-icon {
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.1); opacity: 0.8; }
}

.stage-label {
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--p-text-color);
}

.progress-bar {
  width: 100%;
}

.progress-pct-text {
  font-size: 0.9rem;
  color: var(--p-text-muted-color);
}

.status-message {
  font-size: 0.9rem;
  color: var(--p-text-muted-color);
  font-style: italic;
}

.error-icon {
  margin-bottom: 0.5rem;
}

.error-message {
  color: var(--p-red-600);
  font-weight: 500;
}

.mt-3 {
  margin-top: 0.75rem;
}
</style>
