import axios from 'axios';
import type { Order, Policy, PolicyVersion, PushStatus } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

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

export default api;
