// Barrel: re-export 所有分模块的类型
// 现有 import { Order, Policy } from '../types' 仍然有效
// 但更推荐 named import: import { Order } from '../types/order'
//
// 命名约定:
//   - types/order.ts   - 工单域 (Order, PolicyVersion, UploadRequest)
//   - types/policy.ts  - 策略域 (Policy, UpdatePoliciesRequest)
//   - types/push.ts    - 推送域 V1 (PushStatus, PushProgress, PushLog, PushStatusUpdate)
//   - types/preview.ts - 预览域 (NATInfo, NATPolicy, PreviewPolicy, PreviewFirewall, FirewallGroup, PreviewData)
//
// V2 推送相关类型 (PushV2Result, PushSnapshot, ...) 仍然在 lib/api.ts 里, 因为跟 fetch wrapper 耦合

export * from './order';
export * from './policy';
export * from './push';
export * from './preview';
