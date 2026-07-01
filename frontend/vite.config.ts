import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const appMode = env.VITE_APP_MODE || 'user'
  return {
    plugins: [vue()],
    resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
          changeOrigin: true
        }
      }
    },
    build: {
      outDir: appMode === 'admin' ? 'dist-admin' : 'dist-user',
      target: 'es2020',
      chunkSizeWarningLimit: 1800
    },
    optimizeDeps: {
      include: ['neovis.js']
    }
  }
})
