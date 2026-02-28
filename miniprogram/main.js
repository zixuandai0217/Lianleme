import { createSSRApp } from 'vue'
import App from './App.vue'
import uview from 'uview-ui'

export function createApp() {
  const app = createSSRApp(App)

  // 使用 uview UI
  app.use(uview)

  return {
    app
  }
}
