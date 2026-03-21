import { createApp } from 'vue'

import App from './App.vue'
import { applyDesignTokens } from './lib/designTokens'
import './styles.css'

// bootstrap design tokens before mount; shared pastel theme variables power every admin module; verify with vite build and preview
applyDesignTokens()

createApp(App).mount('#app')
