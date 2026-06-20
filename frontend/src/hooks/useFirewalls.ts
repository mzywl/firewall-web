// 防火墙域 hooks
import { useQuery, useMutation } from '@tanstack/react-query';
import * as api from '../lib/api';

/** GET /api/firewalls — 列出所有防火墙 */
export const useFirewalls = () => {
  return useQuery({
    queryKey: ['firewalls'],
    queryFn: () => api.listFirewalls(),
    staleTime: 30_000,  // 防火墙列表变动少, 30s 缓存
  });
};

/** POST /api/firewalls/<id>/test-connection — 测试 SSH 连接 */
export const useTestConnection = () => {
  return useMutation({
    mutationFn: (firewallId: number) => api.testConnection(firewallId),
  });
};
