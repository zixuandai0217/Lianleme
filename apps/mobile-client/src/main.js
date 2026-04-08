import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

// Why: keep uni-compatible app factory while enabling direct H5 entry mounting.
// Scope: mobile-client startup path for browser and shared uni createApp contract.
// Verify: opening `http://localhost:5273/` renders visible content instead of a blank page.
export function createApp() {
  const app = createSSRApp(App)
  app.use(createPinia())
  return { app }
}

// Why: `index.html` loads `/src/main.js` directly in H5 dev, so explicit browser mount is required.
// Scope: H5 browser runtime only (`window` exists); no effect on non-browser targets.
// Verify: root `#app` receives mounted nodes and page content appears at `/`.
if (typeof window !== 'undefined') {
  const { app } = createApp()
  app.mount('#app')
}
