// Push 域类型 (V1 旧版推送状态相关)
// V2 推送相关类型 (PushV2Result / PushSnapshot / PushSnapshotItem / PushLog / PushLogsResponse)
// 仍然在 lib/api.ts 里 (跟 axios 封装同文件, 因为类型紧密耦合于 fetch wrapper)

/** 推送总状态 (V1 旧版, 跟 /api/push/orders/<id>/status 对应) */
export interface PushStatus {
  order_id: number;
  order_status: string;
  total: number;
  success: number;
  failed: number;
  pending: number;
  progress: number;
}

/** 推送进度增量 (旧版 WebSocket 协议用) */
export interface PushProgress {
  progress: number;
  current: number;
  total: number;
  success: number;
  failed: number;
}

/** 推送日志 (旧版 WebSocket 协议用) */
export interface PushLog {
  level: 'info' | 'success' | 'error' | 'warning';
  message: string;
  timestamp: number;
}

/** 推送状态变更事件 (旧版 WebSocket 协议用) */
export interface PushStatusUpdate {
  status: 'processing' | 'completed' | 'failed';
  message: string;
  success_count: number;
  failed_count: number;
}
