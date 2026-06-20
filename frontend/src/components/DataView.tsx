// 统一数据视图组件 - 替代页面里手写的 loading/error/empty 三态
//
// 用法:
//   <DataView query={useOrder(orderId)}>
//     {(order) => <OrderView order={order} />}
//   </DataView>
//
// 自动处理:
//   - loading: 显示居中 Loader2 spinner
//   - error:   显示红色错误 + 重试按钮
//   - empty:   data 是 [] / null / undefined / '' 时显示空状态
//   - render:  成功时调用 children(data)
//
// 也支持不传 query, 直接传 data (已经用 useQuery 解构出来的):
//   const { data, isLoading, error, refetch } = useOrder(orderId)
//   <DataView data={data} loading={isLoading} error={error} onRetry={refetch} isEmpty={(o) => !o}>
//     {(order) => ...}
//   </DataView>

import type { ReactNode } from 'react';
import { Loader2, AlertCircle, Inbox } from 'lucide-react';

export interface DataViewProps<T> {
  /** 直接传 react-query 结果 (推荐) */
  query?: {
    data: T | undefined;
    isLoading: boolean;
    error: unknown;
    refetch?: () => void;
  };
  /** 或手动传 data/loading/error */
  data?: T;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** 判定空状态: 返回 true 显示空状态。默认: data 是 [] / '' / null / undefined */
  isEmpty?: (data: T) => boolean;
  /** 空状态文案 + icon (默认: '暂无数据') */
  emptyText?: string;
  emptyIcon?: ReactNode;
  /** 加载中提示 (默认: '加载中...') */
  loadingText?: string;
  /** 自定义错误展示 (默认: 红框 + 重试按钮) */
  renderError?: (err: unknown, retry: (() => void) | undefined) => ReactNode;
  children: (data: T) => ReactNode;
}

const defaultIsEmpty = <T,>(data: T): boolean => {
  if (data == null) return true;
  if (typeof data === 'string') return data.length === 0;
  if (Array.isArray(data)) return data.length === 0;
  if (typeof data === 'object') return Object.keys(data as object).length === 0;
  return false;
};

export function DataView<T>({
  query,
  data: dataProp,
  loading: loadingProp,
  error: errorProp,
  onRetry,
  isEmpty = defaultIsEmpty,
  emptyText = '暂无数据',
  emptyIcon,
  loadingText = '加载中...',
  renderError,
  children,
}: DataViewProps<T>) {
  // 优先用 query, fallback 到手动 props
  const data = query ? query.data : dataProp;
  const loading = query ? query.isLoading : !!loadingProp;
  const error = query ? query.error : errorProp;
  const retry = onRetry || query?.refetch;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>{loadingText}</span>
      </div>
    );
  }

  if (error) {
    if (renderError) return <>{renderError(error, retry)}</>;
    return (
      <div className="flex flex-col items-center justify-center h-32 gap-3 p-4 border border-red-200 rounded-lg bg-red-50">
        <AlertCircle className="h-6 w-6 text-red-500" />
        <div className="text-sm text-red-700 max-w-md text-center">
          {error instanceof Error ? error.message : '加载失败'}
        </div>
        {retry && (
          <button
            onClick={retry}
            className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
          >
            重试
          </button>
        )}
      </div>
    );
  }

  if (data === undefined || isEmpty(data)) {
    return (
      <div className="flex flex-col items-center justify-center h-32 gap-2 text-muted-foreground">
        {emptyIcon || <Inbox className="h-8 w-8 opacity-30" />}
        <span className="text-sm">{emptyText}</span>
      </div>
    );
  }

  return <>{children(data)}</>;
}
