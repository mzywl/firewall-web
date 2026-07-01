import axios from 'axios';
import type { Order, Policy, PolicyVersion, PreviewData } from '../types';
import { toast } from './toast';

// 同源：空 baseURL，nginx 同域名反代 /api
// 如需直连后端调试，可设 VITE_API_BASE_URL=http://localhost:18000
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ============================================================
// 统一 401/403/500 错误处理
// ============================================================
// - 401: 未登录 / session 过期
// - 403: 权限不足
// - 5xx: 服务器错误
// 业务 4xx (404/422/400 等) 仍由调用方自行 toast.apiError 处理，不全局弹
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      toast.error('未登录或会话已过期', error);
    } else if (status === 403) {
      toast.error('权限不足', error);
    } else if (status && status >= 500) {
      toast.error('服务器错误', error);
    }
    return Promise.reject(error);
  },
);

// ============================================================
// v2 推送相关类型
// ============================================================

export type PushMode = 'deduplicate' | 'force_push' | 'reuse_objects';

export interface PushV2Result {
  success: boolean;
  snapshot_id: number | null;
  batch_id?: string;
  status?: string;
  elapsed_ms?: number;
  counts?: { created?: number; reused?: number; appended?: number; failed?: number };
  commands_total?: number;
  commands_failed?: number;
  error?: string;
}

export interface Firewall {
  id: number;
  name: string;
  alias?: string | null;
  type: string;
  management_ip: string;
  region?: string | null;
  status?: string;
  is_active?: number;
}

export interface TestConnectionResult {
  firewall_id: number;
  firewall_name: string;
  device_type: string;
  success: boolean;
  banner: string;
  version: string;
  error: string | null;
  elapsed_ms: number;
}

export interface PushSnapshot {
  id: number;
  order_id: number;
  firewall_id: number;
  batch_id: string;
  push_mode: string;
  status: 'running' | 'success' | 'failed' | 'partial';
  total_policies: number;
  new_policies: number;
  reused_policies: number;
  appended_policies: number;
  failed_policies: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  error_log: string | null;
  has_fetched_snapshot: boolean;
}

export interface PushSnapshotItem {
  id: number;
  policy_id: number | null;
  match_key: string | null;
  action: string;
  device_policy_id: string | null;
  device_policy_name: string | null;
  device_src_obj: string | null;
  device_dst_obj: string | null;
  device_service_obj: string | null;
  device_schedule_obj: string | null;
  src_addr_key: string | null;
  dst_addr_key: string | null;
  service_key: string | null;
  schedule_key: string | null;
  raw_commands_preview: string;
  error_msg: string | null;
  created_at: string | null;
}

export interface PushLog {
  id: number;
  seq: number;
  stage: string;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
  data: Record<string, unknown> | null;
  created_at: string | null;
}

export interface PushLogsResponse {
  snapshot_id: number;
  snapshot_status: string;
  total: number;
  after_seq: number;
  logs: PushLog[];
}

// 上传 Excel 文件
export const uploadExcel = async (file: File, title?: string, createdBy?: string): Promise<Order> => {
  const formData = new FormData();
  formData.append('file', file);
  if (title) formData.append('title', title);
  if (createdBy) formData.append('created_by', createdBy);

  const { data } = await api.post<Order>('/api/orders/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return data;
};

// 获取工单详情
export const getOrder = async (orderId: number): Promise<Order> => {
  const { data } = await api.get<Order>(`/api/orders/${orderId}`);
  return data;
};

// 获取策略列表
export const getPolicies = async (
  orderId: number,
  version?: 'original' | 'formatted_v1' | 'formatted_v2' | 'user_modified'
): Promise<Policy[]> => {
  const params = version ? { version } : {};
  const { data } = await api.get<Policy[]>(`/api/orders/${orderId}/policies`, { params });
  return data;
};

// 获取版本列表
export const getVersions = async (orderId: number): Promise<PolicyVersion[]> => {
  const { data } = await api.get<PolicyVersion[]>(`/api/orders/${orderId}/versions`);
  return data;
};

// 更新策略
export const updatePolicies = async (orderId: number, policies: Policy[]): Promise<{ message: string; updated_count: number }> => {
  const { data } = await api.put(`/api/orders/${orderId}/policies`, policies);
  return data;
};

// 删除单条策略 (C2 后端 DELETE /api/orders/{id}/policies/{pid} 端点, status 204)
// 用途: preview 页直接删除用户不想要的策略, 同时清理 user_modified 快照
// (2026-06-28 Execution Plan 重构后, Preview 页不再调用 — 用 PUT /plan/ignore 替代
//  本函数保留兼容其他场景, 例如 Edit 页直接删物理 Policy)
export const deletePolicy = async (orderId: number, policyId: number): Promise<void> => {
  await api.delete(`/api/orders/${orderId}/policies/${policyId}`);
};

// ============================================================
// Execution Plan (2026-06-28) — Preview 页专用接口
// ============================================================
//
// 新架构下 Preview 页只是 "渲染器 + 开关触发器":
//   - GET  /preview           → 拉后端生成好的 plan_data (含 row_uuid + is_ignored)
//   - PUT  /plan/ignore       → 软删除/恢复单行 (用 row_uuid 寻址)
//   - POST /commit            → 把快照里的 is_ignored=false 行写入物理 policies 表
//
// 前端不再比对原始表格 + 合并结果, 拿到什么渲染什么
// (老接口 DELETE /policies/{pid} 还保留供 Edit 页使用)

// 切换单行的 is_ignored (软删除/恢复)
// row_uuid: 后端给每行分配的 UUID, 唯一标识一行预览策略
// ignore:   true = 软删除 (变灰), false = 恢复 (正常)
export const togglePlanRowIgnore = async (
  orderId: number,
  rowUuid: string,
  ignore: boolean,
): Promise<{ message: string; row_uuid: string; is_ignored: boolean }> => {
  const { data } = await api.put(`/api/workorders/${orderId}/plan/ignore`, {
    row_uuid: rowUuid,
    ignore,
  });
  return data;
};

// 提交工单: 把 Execution Plan 快照写入物理 policies 表
// (后端用 plan_data 里每行的 is_ignored 标记 push_status: true→'ignored', false→'pending')
// 不需要在 body 传任何数据 — 后端直接从 PolicyVersion.execution_plan 读
export const commitOrder = async (
  orderId: number,
): Promise<{ message: string; inserted_count: number }> => {
  const { data } = await api.post(`/api/workorders/${orderId}/commit`);
  return data;
};

// ============================================================
// v2 推送 + 防火墙 + 快照
// ============================================================

// (2026-06-28) /api/push/orders/<id>/tasks 原始响应类型 (精简版 — Push 页只用于列墙)
// 字段集是 user 拍板的最小集: firewall 4 字段 + policies 4 字段 (id + src/dst IP + service)
// 不含 NAT / zone / 系统名 / 时间 — 那些由 /generate-script 按墙按需补
export interface PushTaskFirewallRaw {
  id: number;
  name: string;
  type: string;
  management_ip: string;
}

export interface PushTaskPolicyRaw {
  policy_id: number;
  src_ip: string;
  dst_ip: string;
  service: string;
}

export interface PushTaskRaw {
  firewall: PushTaskFirewallRaw;
  policies: PushTaskPolicyRaw[];
}

export interface PushTasksRawResponse {
  order_id: number;
  total_firewalls: number;
  total_policies: number;
  tasks: PushTaskRaw[];
}

/**
 * Push 页进入时调用 — 列该工单下所有 pending 策略(按防火墙分组)
 *
 * 返回 shape 经过适配, 兼容旧 PreviewData 接口 (Push.tsx 大量引用 previewData.firewall_groups)
 * 适配原则 (2026-06-28 精简):
 *   - firewall 4 字段直传 + 补 alias/belong_region/is_zone_boundary/auto_push 默认空值
 *   - policies 字段: src_ip/dst_ip/service 直传 + 补全 PreviewPolicy 必填字段 (action=row, row_uuid=fake, ...)
 */
export const getPushTasks = async (orderId: number): Promise<PreviewData> => {
  const { data } = await api.get<PushTasksRawResponse>(`/api/push/orders/${orderId}/tasks`);

  return {
    order: {
      id: data.order_id,
      // order_no/title/status/created_at 由 Push 页另外通过 useOrder 单独拉
      order_no: '',
      title: '',
      status: '',
      created_at: '',
    },
    firewall_groups: data.tasks.map((task) => ({
      firewall: {
        id: task.firewall.id,
        name: task.firewall.name,
        alias: '',
        type: task.firewall.type,
        management_ip: task.firewall.management_ip,
        belong_region: '',
        is_zone_boundary: 0,
        auto_push: 0,
      },
      policies: task.policies.map((p, idx) => ({
        row_uuid: `task-${p.policy_id}-${idx}`,  // 假 UUID, Push 页不依赖
        is_ignored: false,
        id: p.policy_id,
        sequence: idx + 1,
        original_policy_id: p.policy_id,
        source_zone: '',
        source_ip: p.src_ip,
        dest_zone: '',
        dest_ip: p.dst_ip,
        service: p.service,
        action: 'permit',
        nat_info: {
          need_nat: false,
          nat_type: null,
          snat_address: null,
          dnat_address: null,
          source_zone: null,
          dest_zone: null,
          source_zone_name: '',
          dest_zone_name: '',
          warnings: [],
        },
        nat_policies: [],
      })),
    })),
    unmatched_policies: [],
    warnings: [],
    errors: [],
  };
};

// 列出所有防火墙（精简字段）
export const listFirewalls = async (): Promise<Firewall[]> => {
  const { data } = await api.get<Firewall[]>('/api/firewalls', {
    params: { limit: 500 },
  });
  return data;
};

// 测试 SSH 连接
export const testConnection = async (firewallId: number): Promise<TestConnectionResult> => {
  const { data } = await api.post<TestConnectionResult>(
    `/api/push/test-connection/${firewallId}`,
  );
  return data;
};

// 启动 v2 推送
export const startPushV2 = async (
  orderId: number,
  firewallId: number,
  mode: PushMode = 'deduplicate',
): Promise<PushV2Result> => {
  const { data } = await api.post<PushV2Result>(
    `/api/push/orders/${orderId}/start-v2`,
    null,
    { params: { firewall_id: firewallId, mode } },
  );
  return data;
};

// 查快照详情
export const getSnapshot = async (snapshotId: number): Promise<PushSnapshot> => {
  const { data } = await api.get<PushSnapshot>(`/api/push/snapshots/${snapshotId}`);
  return data;
};

// 查快照明细（分页）
export const getSnapshotItems = async (
  snapshotId: number,
  limit = 100,
  offset = 0,
): Promise<{ snapshot_id: number; total: number; items: PushSnapshotItem[] }> => {
  const { data } = await api.get(`/api/push/snapshots/${snapshotId}/items`, {
    params: { limit, offset },
  });
  return data;
};

// 查快照实时日志（after_seq 用于增量轮询）
export const getSnapshotLogs = async (
  snapshotId: number,
  afterSeq = 0,
): Promise<PushLogsResponse> => {
  const { data } = await api.get<PushLogsResponse>(
    `/api/push/snapshots/${snapshotId}/logs`,
    { params: { after_seq: afterSeq, limit: 200 } },
  );
  return data;
};
export default api;
