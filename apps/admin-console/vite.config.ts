import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    // Why: forward /v1 API calls to gateway in local dev and avoid browser CORS issues.
    // Scope: admin-console local development server only.
    // Verify: GET http://localhost:5174/v1/admin/users returns HTTP 200.
    proxy: {
      '/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
