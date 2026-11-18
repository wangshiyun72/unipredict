import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式：前端 5173 端口，/api 请求代理到后端 8000 端口
// 生产模式：npm run build 生成 dist/，由后端直接提供（单端口 8000）
export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/docs': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/openapi.json': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  },
  build: {
    chunkSizeWarningLimit: 2000
  }
})
