// 全局 ErrorBoundary
// 兜底任何 React 渲染异常 → 不再白屏，弹一个 toast 错误 + 友好 fallback UI
//
// 用法: <ErrorBoundary>{children}</ErrorBoundary> 包裹可能崩的子树
//      或在 main.tsx 包裹整个 <App /> 做最外层兜底

import { Component, type ReactNode, type ErrorInfo } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { toast } from '../lib/toast';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 上报到 sonner toast（开发可见）+ console（生产可对接 Sentry 等）
    toast.error('页面渲染出错', error);
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    // 简单重置：清空 query 缓存避免脏数据
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 gap-4">
          <AlertTriangle className="h-12 w-12 text-red-500" />
          <div className="text-lg font-semibold">页面出错了</div>
          <div className="text-sm text-muted-foreground max-w-md text-center">
            {this.state.error?.message || '组件渲染时发生异常'}
          </div>
          <button
            onClick={this.handleReset}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
          >
            <RefreshCw className="h-4 w-4" />
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
