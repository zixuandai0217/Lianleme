import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
  plugins: [uni()],
  server: {
    // shift the mobile H5 preview and proxy to quieter local ports; mobile-client dev server only; verify with http://127.0.0.1:5273 and proxied /v1 calls to :18000
    port: 5273,
    proxy: {
      '/v1': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
    },
  },
})
