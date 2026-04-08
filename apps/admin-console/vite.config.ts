import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // shift the admin dev server to a quieter local port range; admin-console Vite server and proxy only; verify with http://127.0.0.1:5274 and proxied /v1 calls to :18000
    port: 5274,
    proxy: {
      '/v1': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
    },
  },
})
