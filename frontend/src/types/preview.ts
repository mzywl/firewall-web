// Preview 页面专用类型
// 后端 /api/workorders/<id>/preview 返回的字段 (部分英文字段是后端直接传, 部分中文字段是 SQL JSON 快照里来的)

/**
 * NAT 分析结果 (后端 NATAnalyzer.analyze_policy 返回的 dict)
 *
 * 字段语义双轨:
 *   source_zone / dest_zone: 程序判定的 'internal' | 'external' | null
 *   source_zone_name / dest_zone_name: 业务名 (firewall.local_zone_name / external_zone_name), UI 展示用
 *
 * 坑点 10: 切勿混用 — frontend 必须用 *_zone_name, 程序逻辑才用 *_zone
 */
export interface NATInfo {
  need_nat: boolean;
  nat_type: 'SNAT' | null;   // 项目已取消 DNAT 分析, 永远只会是 'SNAT' 或 null
  snat_address: string | null;
  dnat_address: null;        // 保留字段以兼容, 永远为 null
  source_zone: string | null;
  dest_zone: string | null;
  source_zone_name: string | null;
  dest_zone_name: string | null;
  warnings: string[];
}

/**
 * NAT 转换后生成的策略行 (SNAT 蓝色行 / PASS_THROUGH 绿色行)
 *
 * 坑点: PASS_THROUGH 行的 source_zone / dest_zone 用**当前 firewall** 视角的 zone_name
 *       (不是 region_nat_state 里的边界墙 zone_name)
 *
 * 2026-06-22 C3: 加 original_source_ip 字段 (C2 后端 chain_planner 透传),
 *   PASS_THROUGH 行前端展示 "原 src=xxx" 让用户看流量从哪个原始 IP 来
 */
export interface NATPolicy {
  type: 'SNAT' | 'PASS_THROUGH';
  source_zone: string;
  source_ip: string;
  original_source_ip?: string;
  dest_zone: string;
  dest_ip: string;
  service: string;
  action: string;
  via_firewall?: { id: number; name: string };
}

/**
 * Preview 页面里的策略 (跟 types/index.ts 里的 Policy 不同, 因为字段集合不一样)
 *
 * 字段说明:
 *   - source_zone / dest_zone: Excel 原始业务名 (中文)
 *   - source_ip / dest_ip / service: 单 IP 拆分后值, 可能含 \n 多行
 *   - 使用时间: 来自 user_modified 快照, 没编辑过则空字符串
 */
export interface PreviewPolicy {
  id: number;
  sequence?: number;
  original_policy_id?: number;
  source_zone: string;       // Excel 业务名
  source_ip: string;
  dest_zone: string;         // Excel 业务名
  dest_ip: string;
  service: string;
  action: string;
  nat_info: NATInfo;
  nat_policies: NATPolicy[];
  not_pushed_reason?: string;
  使用时间?: string;
}

/**
 * 防火墙 (preview 路由只返回部分字段, 注意跟 types/index.ts 里的不一样)
 *
 * 2026-06-22 C3 对齐:
 *   - region → belong_region (spec §1 重命名)
 *   - 删 push_contact (spec §1 删除字段)
 *   - 加 is_zone_boundary (前端用 "将在此墙推送" 标识)
 */
export interface PreviewFirewall {
  id: number;
  name: string;
  alias: string;
  type: string;
  management_ip: string;
  belong_region: string;
  is_zone_boundary: number;
  auto_push: number;
}

export interface FirewallGroup {
  firewall: PreviewFirewall;
  policies: PreviewPolicy[];
}

export interface PreviewOrder {
  id: number;
  order_no: string;
  title: string;
  status: string;
  created_at: string;
}

export interface PreviewData {
  order: PreviewOrder;
  firewall_groups: FirewallGroup[];
  unmatched_policies: PreviewPolicy[];
  warnings: string[];
  errors: string[];
}

// ============================================================
// 推送脚本（dry-run）响应类型
// ============================================================
//
// POST /api/push/orders/{order_id}/generate-script?firewall_id=X
// 返回 — 见 backend/app/api/push.py generate_push_script
//
// 用途: 不连设备 / 不复用现有对象 / 纯本地生成 CLI 命令脚本
//       前端用 Modal 弹窗显示, 复制给运维手工执行

export interface GenerateScriptSkipped {
  policy_id: number;
  source_ip: string;
  dest_ip: string;
  reason: string;
}

export interface GenerateScriptNewPolicy {
  policy_id: number;
  rule_name: string;
  src_ips: string[];
  dst_ips: string[];
  ports: string[];
  valid_until: string;
  src_zone: string;
  dst_zone: string;
  action: string;
  // C8 接入 PrePushAnalyzer 后的额外字段
  match_mode?: 'FULL_MATCH' | 'TIME_UPDATE' | 'NEW_RULE';
  reused_rule_name?: string | null;
  reused_rule_content?: string | null;
  push_script?: string[];
  audit_message?: string;
}

export interface GenerateScriptStats {
  total_order_policies: number;
  to_push: number;
  skipped: number;
  commands: number;
  // C8 接入 PrePushAnalyzer 后的 3 mode 计数
  full_match?: number;
  time_update?: number;
  new_rule?: number;
}

export interface GenerateScriptResponse {
  success: boolean;
  firewall: {
    id: number;
    name: string;
    type: string;
    management_ip: string;
  };
  order: {
    id: number;
    order_no: string;
    title: string;
  };
  stats: GenerateScriptStats;
  new_policies: GenerateScriptNewPolicy[];
  policies?: GenerateScriptNewPolicy[];  // C8: 跟 new_policies 同义, 保留兼容
  commands: string[];
  skipped: GenerateScriptSkipped[];
  device_config_fetched?: boolean;
  fetch_error?: string | null;
}
