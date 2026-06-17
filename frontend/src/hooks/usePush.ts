// 推送域 hooks (v2 推送 + 快照 + 实时日志)
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../lib/api';

/** POST /api/push/orders/<id>/start-v2 — 启动 v2 推送 */
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

/** GET /api/push/snapshots/<id> — 查快照状态 */
export const useSnapshot = (snapshotId: number | null) => {
  return useQuery({
    queryKey: ['snapshot', snapshotId],
    queryFn: () => api.getSnapshot(snapshotId!),
    enabled: !!snapshotId,
  });
};

/** GET /api/push/snapshots/<id>/items — 查快照明细 */
export const useSnapshotItems = (snapshotId: number | null) => {
  return useQuery({
    queryKey: ['snapshot-items', snapshotId],
    queryFn: () => api.getSnapshotItems(snapshotId!),
    enabled: !!snapshotId,
  });
};

/**
 * GET /api/push/snapshots/<id>/logs?after_seq=N — 实时日志轮询
 * intervalMs 默认 1500ms, 调用方可用 enabled=false 暂停
 */
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
