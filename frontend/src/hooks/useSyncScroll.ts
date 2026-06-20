// useSyncScroll — 双向同步两个可滚动元素的 scrollLeft
// 用于"上表只读 + 下表可编辑"的列对齐场景 (见 SyncScrollTable)
//
// 用法:
//   const topRef = useRef<HTMLDivElement>(null)
//   const bottomRef = useRef<HTMLDivElement>(null)
//   useSyncScroll(topRef, bottomRef)
//
// 实现细节:
//   - isScrollingRef 防互相触发 (A 滚 → 设 B → B onScroll 又想设 A → 死循环)
//   - requestAnimationFrame 把 scrollLeft 赋值推迟到下一帧, 避免抖动
//
// 后期如果要做列固定 / 横向虚拟化, 把这个 hook 换成第三方实现 (如 react-sync-scroll) 即可

import { useRef, useCallback } from 'react'

export type SyncScrollRef<T extends HTMLElement = HTMLDivElement> =
  React.RefObject<T | null>

export function useSyncScroll(
  refA: SyncScrollRef,
  refB: SyncScrollRef,
) {
  // 防互相触发的 latch
  const isSyncingRef = useRef(false)

  const makeHandler = useCallback(
    (source: SyncScrollRef, target: SyncScrollRef) => () => {
      if (isSyncingRef.current) return
      const sourceEl = source.current
      const targetEl = target.current
      if (!sourceEl || !targetEl) return

      isSyncingRef.current = true
      requestAnimationFrame(() => {
        if (sourceEl && targetEl) {
          targetEl.scrollLeft = sourceEl.scrollLeft
        }
        isSyncingRef.current = false
      })
    },
    [],
  )

  // 返回两个 onScroll handler, 绑到对应 ref 的元素上
  return {
    onScrollA: makeHandler(refA, refB),
    onScrollB: makeHandler(refB, refA),
  }
}
