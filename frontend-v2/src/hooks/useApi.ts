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

// 开始推送
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

// 获取推送状态
export const usePushStatus = (orderId: number, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['pushStatus', orderId],
    queryFn: () => api.getPushStatus(orderId),
    enabled: !!orderId && enabled,
    refetchInterval: 2000, // 每2秒刷新一次
  });
};
