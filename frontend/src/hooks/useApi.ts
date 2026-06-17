// Barrel re-export 所有 domain hooks
// 现有 import { useOrder, usePolicies, ... } from '../hooks/useApi' 仍然有效
// 但更推荐 named import:
//   import { useOrder } from '../hooks/useOrders'
//   import { usePolicies } from '../hooks/useOrders'
//   import { useStartPushV2 } from '../hooks/usePush'
//   import { useFirewalls } from '../hooks/useFirewalls'
//   import { useUploadExcel } from '../hooks/useUpload'
//
// 命名约定:
//   - useOrders.ts    - 工单 + 策略 (useOrder, usePolicies, useUpdatePolicies)
//   - useUpload.ts    - 文件上传 (useUploadExcel)
//   - usePush.ts      - 推送 v2 + 快照 (useStartPushV2, useSnapshot, useSnapshotItems, useSnapshotLogs)
//   - useFirewalls.ts - 防火墙 (useFirewalls, useTestConnection)
//
// 历史: 早期所有 hooks 都堆在这个文件里 (161 行装 14 个 hooks)
// 现已按 domain 拆分, 死代码 (useVersions / useStartPush / useMergePolicies / usePushStatus) 已删除

export * from './useOrders';
export * from './useUpload';
export * from './usePush';
export * from './useFirewalls';
