// Vitest 全局 setup
// - jest-dom matchers (toBeInTheDocument 等)
// - sonner toast 测试时的容器清理
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})
