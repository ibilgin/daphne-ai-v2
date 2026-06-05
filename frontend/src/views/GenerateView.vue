<template>
  <div class="generate-view">
    <div class="generate-header">
      <Button
        icon="pi pi-arrow-left"
        text
        label="Back to Library"
        @click="$router.push('/')"
      />
      <h1>Create a New Comic</h1>
    </div>

    <div class="stepper-wrapper">
      <Stepper :value="activeStep" linear>
        <!-- Step 1: Upload drawing -->
        <StepList>
          <Step value="1">Your Drawing</Step>
          <Step value="2">Choose Style</Step>
          <Step value="3">Creating Comic</Step>
        </StepList>

        <StepPanels>
          <!-- Step 1 -->
          <StepPanel value="1">
            <div class="step-content">
              <h2 class="step-title">Upload your child's drawing</h2>
              <p class="step-desc">A photo or scan of any drawing works great.</p>

              <div class="upload-area">
                <FileUpload
                  ref="fileUploadRef"
                  mode="advanced"
                  accept="image/*"
                  :max-file-size="5242880"
                  :multiple="false"
                  :auto="false"
                  choose-label="Choose Drawing"
                  :show-upload-button="false"
                  :show-cancel-button="false"
                  @select="onFileSelect"
                  class="upload-component"
                >
                  <template #empty>
                    <div class="upload-empty">
                      <i class="pi pi-upload" style="font-size: 2rem" />
                      <p>Drag and drop a drawing here, or click to browse</p>
                      <p class="upload-hint">Images only, max 5 MB</p>
                    </div>
                  </template>
                </FileUpload>

                <div v-if="previewUrl" class="preview-wrapper">
                  <img :src="previewUrl" alt="Drawing preview" class="drawing-preview" />
                </div>
              </div>

              <div class="form-fields">
                <div class="field">
                  <label for="childName">Child's Name</label>
                  <InputText
                    id="childName"
                    v-model="form.childName"
                    placeholder="e.g. Lily"
                    class="w-full"
                  />
                </div>

                <div class="field">
                  <label for="ageGroup">Age Group</label>
                  <Select
                    id="ageGroup"
                    v-model="form.ageGroup"
                    :options="ageGroups"
                    option-label="label"
                    option-value="value"
                    placeholder="Select age group"
                    class="w-full"
                  />
                </div>
              </div>

              <div class="step-actions">
                <Button
                  label="Next: Choose Style"
                  icon="pi pi-arrow-right"
                  icon-pos="right"
                  :disabled="!canProceedStep1"
                  @click="activeStep = '2'"
                />
              </div>
            </div>
          </StepPanel>

          <!-- Step 2 -->
          <StepPanel value="2">
            <div class="step-content">
              <h2 class="step-title">Choose your comic style</h2>
              <p class="step-desc">Pick the adventure that suits your child best.</p>

              <div class="style-grid">
                <div
                  v-for="style in styles"
                  :key="style.value"
                  class="style-card"
                  :class="{ selected: form.style === style.value }"
                  @click="form.style = style.value"
                >
                  <div class="style-emoji">{{ style.emoji }}</div>
                  <div class="style-name">{{ style.label }}</div>
                  <div class="style-desc">{{ style.description }}</div>
                </div>
              </div>

              <div class="step-actions">
                <Button
                  label="Back"
                  icon="pi pi-arrow-left"
                  text
                  @click="activeStep = '1'"
                />
                <Button
                  label="Generate Comic"
                  icon="pi pi-sparkles"
                  icon-pos="right"
                  :disabled="!form.style"
                  @click="submitForm"
                  :loading="submitting"
                />
              </div>
            </div>
          </StepPanel>

          <!-- Step 3 -->
          <StepPanel value="3">
            <div class="step-content">
              <h2 class="step-title">Creating your comic</h2>
              <p class="step-desc">This takes about 1-2 minutes. Sit tight!</p>

              <JobStatus
                v-if="store.activeJob?.job_id"
                :job-id="store.activeJob.job_id"
                @complete="onJobComplete"
                @failed="onJobFailed"
              />

              <div v-else class="no-job">
                <ProgressSpinner />
                <p>Submitting your drawing...</p>
              </div>
            </div>
          </StepPanel>
        </StepPanels>
      </Stepper>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import Stepper from 'primevue/stepper'
import StepList from 'primevue/steplist'
import Step from 'primevue/step'
import StepPanels from 'primevue/steppanels'
import StepPanel from 'primevue/steppanel'
import FileUpload from 'primevue/fileupload'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Button from 'primevue/button'
import ProgressSpinner from 'primevue/progressspinner'
import JobStatus from '../components/JobStatus.vue'
import { useComicStore } from '../stores/comic.js'

const router = useRouter()
const store = useComicStore()

const activeStep = ref('1')
const fileUploadRef = ref(null)
const previewUrl = ref(null)
const submitting = ref(false)
const jobError = ref(null)

const form = ref({
  childName: '',
  ageGroup: '',
  style: '',
  file: null,
})

const ageGroups = [
  { label: '4 – 6 years', value: '4-6' },
  { label: '7 – 9 years', value: '7-9' },
  { label: '10 – 12 years', value: '10-12' },
]

const styles = [
  {
    value: 'adventure',
    label: 'Adventure',
    emoji: '🗺️',
    description: 'Brave explorers and exciting quests',
  },
  {
    value: 'fantasy',
    label: 'Fantasy',
    emoji: '🧙',
    description: 'Magic, dragons, and enchanted worlds',
  },
  {
    value: 'friendship',
    label: 'Friendship',
    emoji: '🤝',
    description: 'Stories about kindness and loyalty',
  },
  {
    value: 'mystery',
    label: 'Mystery',
    emoji: '🔍',
    description: 'Puzzles and clues to solve together',
  },
  {
    value: 'animals',
    label: 'Animals',
    emoji: '🐾',
    description: 'Cute creature companions on adventures',
  },
  {
    value: 'space',
    label: 'Space',
    emoji: '🚀',
    description: 'Galactic missions among the stars',
  },
]

const canProceedStep1 = computed(
  () => form.value.file && form.value.childName.trim() && form.value.ageGroup,
)

function onFileSelect(event) {
  const file = event.files?.[0]
  if (!file) return
  form.value.file = file
  previewUrl.value = URL.createObjectURL(file)
}

async function submitForm() {
  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('drawing', form.value.file)
    fd.append('child_name', form.value.childName.trim())
    fd.append('age_group', form.value.ageGroup)
    fd.append('style', form.value.style)

    await store.submitDrawing(fd)
    activeStep.value = '3'
  } catch (err) {
    jobError.value = err.message
  } finally {
    submitting.value = false
  }
}

function onJobComplete(resultId) {
  router.push(`/read/${resultId}`)
}

function onJobFailed(message) {
  jobError.value = message
}
</script>

<style scoped>
.generate-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem;
}

.generate-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
}

.generate-header h1 {
  font-size: 1.6rem;
  font-weight: 700;
}

.stepper-wrapper {
  background: var(--p-surface-card);
  border-radius: 12px;
  padding: 2rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.step-content {
  padding: 1.5rem 0;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.step-title {
  font-size: 1.3rem;
  font-weight: 600;
}

.step-desc {
  color: var(--p-text-muted-color);
}

.upload-area {
  display: flex;
  gap: 1.5rem;
  align-items: flex-start;
}

.upload-component {
  flex: 1;
}

.upload-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem;
  color: var(--p-text-muted-color);
}

.upload-hint {
  font-size: 0.8rem;
}

.drawing-preview {
  width: 140px;
  height: 140px;
  object-fit: cover;
  border-radius: 8px;
  border: 2px solid var(--p-surface-300);
}

.form-fields {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.field {
  flex: 1;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field label {
  font-weight: 500;
  font-size: 0.9rem;
}

.w-full {
  width: 100%;
}

.style-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.style-card {
  border: 2px solid var(--p-surface-300);
  border-radius: 8px;
  padding: 1.2rem;
  cursor: pointer;
  text-align: center;
  transition: border-color 0.2s, background 0.2s;
  background: var(--p-surface-0);
}

.style-card:hover {
  border-color: var(--p-primary-400);
  background: var(--p-primary-50);
}

.style-card.selected {
  border-color: var(--p-primary-500);
  background: var(--p-primary-50);
  box-shadow: 0 0 0 3px var(--p-primary-200);
}

.style-emoji {
  font-size: 2.2rem;
  margin-bottom: 0.4rem;
}

.style-name {
  font-weight: 600;
  font-size: 0.95rem;
}

.style-desc {
  font-size: 0.8rem;
  color: var(--p-text-muted-color);
  margin-top: 0.25rem;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--p-surface-200);
}

.no-job {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 3rem;
  color: var(--p-text-muted-color);
}
</style>
