// DataView 组件测试 - 验证 loading/error/empty/children 四态
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DataView } from './DataView'

describe('DataView', () => {
  // ========== query prop 模式 (与 react-query 配合) ==========
  describe('with query prop', () => {
    it('shows loading state when isLoading=true', () => {
      render(
        <DataView query={{ data: undefined, isLoading: true, error: null }}>
          {() => <div>data</div>}
        </DataView>
      )
      expect(screen.getByText('加载中...')).toBeInTheDocument()
      expect(screen.queryByText('data')).not.toBeInTheDocument()
    })

    it('shows error state with retry button when error present', () => {
      const refetch = vi.fn()
      render(
        <DataView
          query={{ data: undefined, isLoading: false, error: new Error('网络断了'), refetch }}
        >
          {() => <div>data</div>}
        </DataView>
      )
      expect(screen.getByText('网络断了')).toBeInTheDocument()
      fireEvent.click(screen.getByText('重试'))
      expect(refetch).toHaveBeenCalledTimes(1)
    })

    it('shows empty state for empty array', () => {
      render(
        <DataView query={{ data: [], isLoading: false, error: null }}>
          {() => <div>data</div>}
        </DataView>
      )
      expect(screen.getByText('暂无数据')).toBeInTheDocument()
    })

    it('shows empty state for null', () => {
      const { container } = render(
        <DataView query={{ data: null, isLoading: false, error: null }}>
          {() => <div>data</div>}
        </DataView>
      )
      expect(screen.getByText('暂无数据')).toBeInTheDocument()
      expect(container).not.toHaveTextContent('data')
    })

    it('shows empty state for empty string', () => {
      render(
        <DataView query={{ data: '', isLoading: false, error: null }}>
          {() => <div>data</div>}
        </DataView>
      )
      expect(screen.getByText('暂无数据')).toBeInTheDocument()
    })

    it('renders children with data when success', () => {
      render(
        <DataView query={{ data: { name: 'foo' }, isLoading: false, error: null }}>
          {(d) => <div>name={d.name}</div>}
        </DataView>
      )
      expect(screen.getByText('name=foo')).toBeInTheDocument()
    })
  })

  // ========== 手动 props 模式 (已经解构过 query 后) ==========
  describe('with manual props', () => {
    it('respects isEmpty override', () => {
      // 0 是个有效数据, 但 isEmpty 把它当作空 (业务场景: "零条策略" 显示空状态)
      render(
        <DataView
          data={0}
          loading={false}
          error={null}
          isEmpty={(d) => d === 0}
          emptyText="没有策略"
        >
          {(d) => <div>count={d}</div>}
        </DataView>
      )
      expect(screen.getByText('没有策略')).toBeInTheDocument()
    })

    it('loadingText prop overrides default', () => {
      render(
        <DataView loading error={null} data={undefined} loadingText="拼命加载中...">
          {() => <div />}
        </DataView>
      )
      expect(screen.getByText('拼命加载中...')).toBeInTheDocument()
    })

    it('renderError prop overrides default error UI', () => {
      const custom = vi.fn(() => <div>custom error</div>)
      render(
        <DataView
          loading={false}
          error={new Error('boom')}
          data={undefined}
          renderError={custom}
        >
          {() => <div />}
        </DataView>
      )
      expect(custom).toHaveBeenCalled()
      expect(screen.getByText('custom error')).toBeInTheDocument()
    })
  })

  // ========== 优先级 ==========
  describe('prop precedence', () => {
    it('query prop wins over manual props when both provided', () => {
      // query.isLoading=true, 但手动传 loading=false
      // 应该用 query 的
      render(
        <DataView
          query={{ data: undefined, isLoading: true, error: null }}
          loading={false}
          error={null}
          data={undefined}
        >
          {() => <div>data</div>}
        </DataView>
      )
      expect(screen.getByText('加载中...')).toBeInTheDocument()
    })
  })
})
