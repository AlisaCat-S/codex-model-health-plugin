import { fileURLToPath, URL } from 'node:url'
import CodexProxyUI from '@codex-proxy/ui/vite'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  plugins: [vue(), tailwindcss(), CodexProxyUI(), {
    name: 'plugin-classic-script',
    transformIndexHtml: { order: 'post', handler: html => html.replace('type="module" crossorigin', 'defer') },
  }],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    modulePreload: false,
    cssCodeSplit: false,
    rolldownOptions: { output: { format: 'iife', codeSplitting: false, entryFileNames: 'app.js', assetFileNames: 'app.[ext]' } },
  },
})
