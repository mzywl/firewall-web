import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // 生产部署在 nginx 同源时 base = '/'（默认）
  // 如需挂到子路径（如 https://host/firewall/），可设 VITE_BASE=/firewall/
  base: process.env.VITE_BASE || '/',
  server: {
    // 开发模式: 5173 → 后端 18000（vite 自带 proxy，开发无跨域）
    //   前端请求 /api/...  →  后端 /api/...
    //   前端请求 /socket.io/...  →  后端 /socket.io/...
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:18000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
