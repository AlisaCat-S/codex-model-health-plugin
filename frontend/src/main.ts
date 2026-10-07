import { createApp } from 'vue'
import App from './App.vue'
import '@codex-proxy/ui/styles.css'
import './styles/index.css'

if (import.meta.env.DEV && new URLSearchParams(location.search).get('preview') === '1') {
  const { installPreview } = await import('./preview')
  installPreview()
}
createApp(App).mount('#app')
