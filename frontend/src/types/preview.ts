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
 */
export interface NATPolicy {
  type: 'SNAT' | 'PASS_THROUGH';
  source_zone: string;
  source_ip: string;
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
 */
export interface PreviewFirewall {
  id: number;
  name: string;
  alias: string;
  type: string;
  management_ip: string;
  region: string;
  auto_push: number;
  push_contact: string;
  // 注意: preview API 还没回传 is_zone_boundary, 详见 SKILL.md 坑点 (待补)
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
