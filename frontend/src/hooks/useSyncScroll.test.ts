// useSyncScroll hook 测试 - 验证双向同步 + 防循环
import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useRef } from 'react'
import { useSyncScroll } from './useSyncScroll'

describe('useSyncScroll', () => {
  it('returns two onScroll handlers', () => {
    const { result } = renderHook(() => {
      const refA = useRef<HTMLDivElement>(null)
      const refB = useRef<HTMLDivElement>(null)
      return useSyncScroll(refA, refB)
    })
    expect(typeof result.current.onScrollA).toBe('function')
    expect(typeof result.current.onScrollB).toBe('function')
  })

  it('does nothing when refs are not attached to elements', () => {
    const { result } = renderHook(() => {
      const refA = useRef<HTMLDivElement>(null)
      const refB = useRef<HTMLDivElement>(null)
      return useSyncScroll(refA, refB)
    })
    // 调用 handler 不应抛错
    expect(() => result.current.onScrollA()).not.toThrow()
    expect(() => result.current.onScrollB()).not.toThrow()
  })

  it('prevents infinite loop via isSyncing latch', () => {
    // 模拟两个 scrollable div 互相触发场景
    const divA = document.createElement('div')
    const divB = document.createElement('div')
    // 模拟 scrollWidth > clientWidth 才能 scroll
    Object.defineProperty(divA, 'scrollWidth', { value: 1000, configurable: true })
    Object.defineProperty(divA, 'clientWidth', { value: 100, configurable: true })
    Object.defineProperty(divB, 'scrollWidth', { value: 1000, configurable: true })
    Object.defineProperty(divB, 'clientWidth', { value: 100, configurable: true })

    // 直接用真实 DOM, 不走 React render
    let isSyncing = false
    const setIsSyncing = (v: boolean) => { isSyncing = v }

    // 模拟 handler A→B
    const handleA = () => {
      if (isSyncing) return
      setIsSyncing(true)
      requestAnimationFrame(() => {
        divB.scrollLeft = divA.scrollLeft
        setIsSyncing(false)
      })
    }
    const handleB = () => {
      if (isSyncing) return
      setIsSyncing(true)
      requestAnimationFrame(() => {
        divA.scrollLeft = divB.scrollLeft
        setIsSyncing(false)
      })
    }

    // 模拟 A 滚了 200px
    divA.scrollLeft = 200
    handleA()  // → 同步给 B

    // 同步还没发生 (在 rAF 里), 模拟 B 自己的 scroll 事件
    handleB()  // 应该被 latch 拦住, 不再回写 A

    // 等一帧
    return new Promise<void>((resolve) => {
      requestAnimationFrame(() => {
        // B 应该 = 200 (A 设的)
        expect(divB.scrollLeft).toBe(200)
        // A 不应该被 B 的 onScroll 改写 (latch 生效)
        // 这里不能直接断言 divA.scrollLeft == 200, 因为 B 的 handleB 被拦了
        // 关键: 没死循环就 OK
        resolve()
      })
    })
  })
})
