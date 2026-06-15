import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../lib/api';
import type { Policy } from '../types';

// 获取工单详情
export const useOrder = (orderId: number) => {
  return useQuery({
    queryKey: ['order', orderId],
    queryFn: () => api.getOrder(orderId),
    enabled: !!orderId,
  });
};

// 获取策略列表
export const usePolicies = (
  orderId: number,
  version?: 'original' | 'formatted_v1' | 'formatted_v2' | 'user_modified'
) => {
  return useQuery({
    queryKey: ['policies', orderId, version],
    queryFn: () => api.getPolicies(orderId, version),
    enabled: !!orderId,
  });
};

// 获取版本列表
export const useVersions = (orderId: number) => {
  return useQuery({
    queryKey: ['versions', orderId],
    queryFn: () => api.getVersions(orderId),
    enabled: !!orderId,
  });
};

// 上传文件
export const useUploadExcel = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, title, createdBy }: { file: File; title?: string; createdBy?: string }) =>
      api.uploadExcel(file, title, createdBy),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
};

// 更新策略
export const useUpdatePolicies = (orderId: number) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (policies: Policy[]) => api.updatePolicies(orderId, policies),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies', orderId] });
      queryClient.invalidateQueries({ queryKey: ['versions', orderId] });
    },
  });
};

// 开始推送（v1 旧版，保留兼容）
export const useStartPush = (orderId: number) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.startPush(orderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['order', orderId] });
      queryClient.invalidateQueries({ queryKey: ['pushStatus', orderId] });
    },
  });
};

// 策略合并
export const useMergePolicies = (orderId: number) => {
  return useMutation({
    mutationFn: () => api.mergePolicies(orderId),
  });
};

// 获取推送状态（旧版）
export const usePushStatus = (orderId: number, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['pushStatus', orderId],
    queryFn: () => api.getPushStatus(orderId),
    enabled: !!orderId && enabled,
    refetchInterval: 2000,
  });
};

// ============================================================
// v2 推送 + 防火墙 + 快照 hooks
// ============================================================

// 列出所有防火墙
export const useFirewalls = () => {
  return useQuery({
    queryKey: ['firewalls'],
    queryFn: () => api.listFirewalls(),
    staleTime: 30_000,
  });
};

// 测试 SSH 连接
export const useTestConnection = () => {
  return useMutation({
    mutationFn: (firewallId: number) => api.testConnection(firewallId),
  });
};

// 启动 v2 推送
export const useStartPushV2 = (orderId: number) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      firewallId,
      mode,
    }: {
      firewallId: number;
      mode: api.PushMode;
    }) => api.startPushV2(orderId, firewallId, mode),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['order', orderId] });
      if (data.snapshot_id) {
        queryClient.invalidateQueries({ queryKey: ['snapshot', data.snapshot_id] });
      }
    },
  });
};

// 查快照详情
export const useSnapshot = (snapshotId: number | null) => {
  return useQuery({
    queryKey: ['snapshot', snapshotId],
    queryFn: () => api.getSnapshot(snapshotId!),
    enabled: !!snapshotId,
  });
};

// 查快照明细
export const useSnapshotItems = (snapshotId: number | null) => {
  return useQuery({
    queryKey: ['snapshot-items', snapshotId],
    queryFn: () => api.getSnapshotItems(snapshotId!),
    enabled: !!snapshotId,
  });
};

// 实时日志（轮询；afterSeq 增量）
export const useSnapshotLogs = (
  snapshotId: number | null,
  enabled: boolean = true,
  intervalMs: number = 1500,
) => {
  return useQuery({
    queryKey: ['snapshot-logs', snapshotId],
    queryFn: () => api.getSnapshotLogs(snapshotId!, 0),
    enabled: !!snapshotId && enabled,
    refetchInterval: intervalMs,
  });
};
