import { defineStore } from 'pinia'
import axios from 'axios'

// Empty baseURL — all /api/* requests are relative to the current origin
// and are intercepted by the Vite dev-server proxy (or BFF in production).
const api = axios.create({ baseURL: '' })

// Fetch a dev token once and attach it to every subsequent request.
// In production replace this with a real login flow.
let _tokenPromise = null
function ensureToken() {
  if (!_tokenPromise) {
    _tokenPromise = axios.post('/api/auth/token')
      .then(r => {
        api.defaults.headers.common['Authorization'] = `Bearer ${r.data.access_token}`
      })
      .catch(() => {
        _tokenPromise = null // retry on next call if it failed
      })
  }
  return _tokenPromise
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 10 * 60 * 1000 // 10 minutes

export const useComicStore = defineStore('comic', {
  state: () => ({
    library: [],
    currentComic: null,
    activeJob: null,
  }),

  actions: {
    async fetchLibrary() {
      await ensureToken()
      const response = await api.get('/api/comics')
      this.library = response.data
    },

    async fetchComic(id) {
      await ensureToken()
      const response = await api.get(`/api/comics/${id}`)
      this.currentComic = response.data
      return this.currentComic
    },

    async submitDrawing(formData) {
      await ensureToken()
      const response = await api.post('/api/generate-comic', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      this.activeJob = {
        job_id: response.data.job_id,
        status: response.data.status,
        progress_pct: 0,
        stage: 'queued',
      }
      return this.activeJob
    },

    pollJob(jobId) {
      return new Promise((resolve, reject) => {
        const startedAt = Date.now()
        let intervalId = null

        const cleanup = () => {
          if (intervalId !== null) {
            clearInterval(intervalId)
            intervalId = null
          }
        }

        const tick = async () => {
          if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
            cleanup()
            reject(new Error('Job polling timed out after 10 minutes'))
            return
          }

          try {
            const response = await api.get(`/api/jobs/${jobId}`)
            const job = response.data

            // Keep activeJob in sync with latest poll data
            this.activeJob = {
              ...this.activeJob,
              status: job.status,
              progress_pct: job.progress_pct,
              stage: job.stage,
              result_id: job.result_id ?? null,
            }

            if (job.status === 'complete') {
              cleanup()
              resolve(job)
            } else if (job.status === 'failed') {
              cleanup()
              reject(new Error(job.error || 'Job failed'))
            }
            // queued / processing → keep polling
          } catch (err) {
            cleanup()
            reject(err)
          }
        }

        // Run immediately then on interval
        tick()
        intervalId = setInterval(tick, POLL_INTERVAL_MS)
      })
    },
  },
})
