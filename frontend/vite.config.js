import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // API_PROXY_TARGET is a server-only var (no VITE_ prefix) so it is never
  // embedded in the client bundle. Falls back to localhost:3001 for host dev.
  const apiTarget = process.env.API_PROXY_TARGET || env.API_PROXY_TARGET || 'http://localhost:3001'

  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
