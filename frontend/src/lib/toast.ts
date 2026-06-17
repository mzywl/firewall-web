// 统一 toast 封装
//
// 替换原来散落在 8 个文件里的 alert()/confirm()/console.error()，集中处理:
//   - 成功 / 失败 / 信息 / 警告四种语义
//   - 错误信息从 axios error 里提取 detail/message
//   - 401/403/500 区分（由 api.ts interceptor 自动处理）
//   - 确认弹窗用 toast.warning + action 按钮
//
// 用法: import { toast } from '@/lib/toast'
//   toast.success('保存成功')
//   toast.error('保存失败', err)        // err 可选，会自动从 axios error 提取
//   toast.apiError(err, '保存失败')     // 用于 api 调用失败，约定式
//   toast.confirm('确定删除？', { onConfirm: () => doDelete() })

import { toast as sonnerToast, type ExternalToast } from 'sonner';

/** Axios 错误形状（不 extends Error,避免跟 Error.message 必填冲突） */
export interface ApiErrorShape {
  response?: {
    status?: number;
    data?: { detail?: string | Array<{ msg?: string; loc?: unknown }>; message?: string };
  };
  message?: string;
}

/** 从 axios/fetch 错误里提取可读消息 */
export function extractErrorMessage(err: unknown, fallback = '操作失败'): string {
  if (!err) return fallback;
  const e = err as ApiErrorShape;
  // FastAPI 422 / 404 / 500 等: { detail: "..." } 或 { detail: [{msg: "..."}] }
  const detail = e.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => d?.msg)
      .filter((m): m is string => typeof m === 'string');
    if (msgs.length > 0) return msgs.join('; ');
  }
  if (e.response?.data?.message) return e.response.data.message;
  if (typeof e.message === 'string' && e.message) return e.message;
  return fallback;
}

export const toast = {
  success(message: string, opts?: ExternalToast) {
    sonnerToast.success(message, opts);
  },
  info(message: string, opts?: ExternalToast) {
    sonnerToast.info(message, opts);
  },
  warning(message: string, opts?: ExternalToast) {
    sonnerToast.warning(message, opts);
  },
  error(message: string, err?: unknown, opts?: ExternalToast) {
    sonnerToast.error(message, {
      description: err ? extractErrorMessage(err) : undefined,
      ...opts,
    });
  },
  /** api 调用失败的约定式调用，自动从 error 提取 detail */
  apiError(err: unknown, fallback = '操作失败') {
    sonnerToast.error(fallback, { description: extractErrorMessage(err) });
  },
  /**
   * 危险操作确认（替代 window.confirm）
   * 用 toast.warning + 取消按钮 + 确认按钮，10s 自动消失
   */
  confirm(message: string, opts: { onConfirm: () => void; confirmText?: string; cancelText?: string }) {
    sonnerToast.warning(message, {
      duration: 10_000,
      action: {
        label: opts.confirmText || '确认',
        onClick: () => opts.onConfirm(),
      },
      cancel: {
        label: opts.cancelText || '取消',
        onClick: () => {},
      },
    });
  },
};
