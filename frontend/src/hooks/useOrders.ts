// 订单域 hooks (单条工单 + 策略列表)
// 所有 hooks 通过 react-query 缓存, queryKey 格式: ['<domain>', orderId, ...filters]
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../lib/api';
import type { Policy } from '../types';

/** GET /api/orders/<id> — 单条工单 */
export const useOrder = (orderId: number) => {
  return useQuery({
    queryKey: ['order', orderId],
    queryFn: () => api.getOrder(orderId),
    enabled: !!orderId,
  });
};

/**
 * GET /api/orders/<id>/policies?version=...
 * version 不传 → 当前 Policy 表数据 (可编辑)
 * 传 'original' / 'formatted_v1' / 'formatted_v2' / 'user_modified' → 快照数据 (只读)
 */
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

/** PUT /api/orders/<id>/policies — 批量更新策略 (含 FIELD_MAP 中→英) */
export const useUpdatePolicies = (orderId: number) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (policies: Policy[]) => api.updatePolicies(orderId, policies),
    onSuccess: () => {
      // 失效当前工单的所有策略缓存 (含 version 变体)
      queryClient.invalidateQueries({ queryKey: ['policies', orderId] });
    },
  });
};
