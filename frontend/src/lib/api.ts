import axios from 'axios';
import type { Order, Policy, PolicyVersion, PushStatus } from '../types';

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
// v2 推送相关类型
// ============================================================

export type PushMode = 'deduplicate' | 'force_push';

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

// 开始推送
export const startPush = async (orderId: number): Promise<{ message: string; task_id: string; order_id: number; policies_count: number }> => {
  const { data } = await api.post(`/api/push/orders/${orderId}/start`);
  return data;
};

// 策略合并分析
export const mergePolicies = async (orderId: number): Promise<{
  message: string;
  original_count: number;
  merged_count: number;
  redundant_count: number;
  redundant_ids: number[];
  merged_policies: Policy[];
}> => {
  const { data } = await api.post(`/api/push/orders/${orderId}/merge`);
  return data;
};

// 获取推送状态
export const getPushStatus = async (orderId: number): Promise<PushStatus> => {
  const { data } = await api.get<PushStatus>(`/api/push/orders/${orderId}/status`);
  return data;
};

// ============================================================
// v2 推送 + 防火墙 + 快照
// ============================================================

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

// 列出某防火墙的历史快照
export const listFirewallSnapshots = async (
  firewallId: number,
  limit = 20,
  offset = 0,
): Promise<{ firewall_id: number; firewall_name: string; total: number; snapshots: PushSnapshot[] }> => {
  const { data } = await api.get(
    `/api/push/firewall/${firewallId}/snapshots`,
    { params: { limit, offset } },
  );
  return data;
};

export default api;
