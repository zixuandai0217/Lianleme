import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
  plugins: [uni()],
  server: {
    // Why: use local proxy so mobile H5 can call gateway via same-origin /v1 path.
    // Scope: development-time API requests from mobile-client only.
    // Verify: GET http://localhost:5173/v1/home/workout returns HTTP 200.
    proxy: {
      '/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
