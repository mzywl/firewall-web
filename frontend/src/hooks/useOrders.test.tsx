// useUpdatePolicies hook 测试 - 验证 cache invalidation 流程
// 这个就是 audit 说"中文字段默默吞了"的根因 — 通过测试固化 FIELD_MAP 行为
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useUpdatePolicies } from './useOrders'

// 桩 MSW server
// 注意: api.ts 用空 baseURL + 相对路径 /api/..., 所以 msw handler 用相对路径
const server = setupServer()

beforeEach(() => {
  server.listen({ onUnhandledRequest: 'bypass' })
  return () => server.close()
})

// 包一个 wrapper with fresh QueryClient
const makeWrapper = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useUpdatePolicies', () => {
  it('sends PUT to /api/orders/<id>/policies', async () => {
    const putSpy = vi.fn()
    server.use(
      http.put('/api/orders/18/policies', async ({ request }) => {
        const body = await request.json()
        putSpy(body)
        return HttpResponse.json({ message: '策略更新成功', updated_count: 1 })
      })
    )

    const { result } = renderHook(() => useUpdatePolicies(18), {
      wrapper: makeWrapper(),
    })

    result.current.mutate([{ id: 1, 源IP: '10.1.1.1', 使用时间: '长期' }] as any)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(putSpy).toHaveBeenCalledWith([
      { id: 1, 源IP: '10.1.1.1', 使用时间: '长期' },
    ])
  })

  it('invalidates policies query on success (caches are stale-marked)', async () => {
    server.use(
      http.put('/api/orders/18/policies', () =>
        HttpResponse.json({ message: 'ok', updated_count: 1 })
      )
    )

    // 用闭包捕获 qc, 因为 hook render 在 wrapper 内部, 外部拿不到
    let qcRef: QueryClient | null = null
    const { result } = renderHook(
      () => useUpdatePolicies(18),
      {
        wrapper: ({ children }) => {
          const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
          qcRef = qc
          return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
        },
      }
    )

    // 预填两个 policies 缓存, 模拟"用户编辑前页面已加载"
    qcRef!.setQueryData(['policies', 18, undefined], [{ id: 1, source_ip: 'old' }])
    qcRef!.setQueryData(['policies', 18, 'user_modified'], [{ id: 1, 使用时间: 'old' }])

    result.current.mutate([{ id: 1, source_ip: 'new' }] as any)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // 关键: invalidate 后, getQueryState 应该返回 isInvalidated=true
    const state1 = qcRef!.getQueryState(['policies', 18, undefined])
    const state2 = qcRef!.getQueryState(['policies', 18, 'user_modified'])
    expect(state1?.isInvalidated).toBe(true)
    expect(state2?.isInvalidated).toBe(true)
  })

  it('surfaces API error from backend (FastAPI detail)', async () => {
    server.use(
      http.put('/api/orders/18/policies', () =>
        HttpResponse.json({ detail: '工单不存在' }, { status: 404 })
      )
    )

    const { result } = renderHook(() => useUpdatePolicies(18), {
      wrapper: makeWrapper(),
    })

    result.current.mutate([{ id: 1, source_ip: 'x' }] as any)

    await waitFor(() => expect(result.current.isError).toBe(true))
    // 401/403/5xx 在 api.ts interceptor 已经 toast 了, 4xx 不全局弹, 由调用方处理
    expect((result.current.error as any).response.status).toBe(404)
  })
})
