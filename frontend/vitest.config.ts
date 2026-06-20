/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// vitest 独立配置 — 跟 vite.config.ts 解耦
// (vite.config.ts 不能同时给 vite + vitest 用, 因为 vitest 专属类型需要 vitest/config)
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,  // 跳过 CSS import, 测试不需要
  },
})
