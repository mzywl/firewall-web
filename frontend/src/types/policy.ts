// Policy 域类型
// Edit 页用 (英文 source_ip/dest_ip/service 字段, 跟后端 Policy ORM 一致)
//
// 注意: 跟 types/preview.ts 的 PreviewPolicy 是不同的概念:
//   - Policy (本文件): Edit 页用, 简单结构, 英文字段
//   - PreviewPolicy: Preview 页用, 包含 nat_info, nat_policies, 使用时间 等扩展字段

/** Edit 页用的策略 (跟后端 Policy ORM 一一对应) */
export interface Policy {
  id?: number;
  order_id?: number;
  source_zone: string;
  dest_zone: string;
  source_ip: string;
  dest_ip: string;
  service: string;
  action: string;
  firewall_id?: number | null;
  push_status?: 'success' | 'failed' | null;
  push_message?: string | null;
}

/** 批量更新策略请求 (PUT /api/orders/<id>/policies) */
export interface UpdatePoliciesRequest {
  policies: Policy[];
}
