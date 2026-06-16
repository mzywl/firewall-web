"""
策略预览API V2 - 完全重写
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from app.database import get_db
from app.models import Order, Policy, Firewall
from app.core.firewall_matcher import FirewallMatcher, NOT_PUSHED_REASONS
from app.core.nat_analyzer import NATAnalyzer
from app.core.policy_splitter_v2 import PolicySplitterV2, PolicyMergerV2

router = APIRouter(prefix="/api/workorders", tags=["preview"])


@router.get("/{order_id}/preview")
def get_preview_data(order_id: int, db: Session = Depends(get_db)):
    """
    获取策略预览数据 V2
    
    核心逻辑：
    1. 读取Excel策略（一行可能包含多个源/目的IP）
    2. 拆分成单IP策略（笛卡尔积）
    3. 每个单IP策略匹配防火墙
    4. 按防火墙分组
    5. 每个防火墙内执行三步合并
    6. 添加序号
    """
    # 查询工单
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 查询所有策略
    policies = db.query(Policy).filter(Policy.order_id == order_id).all()
    
    # 初始化
    splitter = PolicySplitterV2(db)
    nat_analyzer = NATAnalyzer(db)
    
    # 按防火墙分组
    firewall_groups = {}  # {firewall_id: {'firewall': Firewall, 'policies': []}}
    not_pushed_policies = []  # 不推送的策略
    warnings = []
    errors = []

    # region 维度的 NAT 透传状态: 同 region 内前序边界墙 SNAT 转换后的 IP
    # 结构: { region: {"translated_src_ip": str, "translated_dst_ip": str|None,
    #                   "source_zone": str, "dest_zone": str,
    #                   "via_firewall": {"id": int, "name": str}} }
    region_nat_state: Dict[str, Dict] = {}

    # 第一步：拆分所有策略为单IP策略
    for policy in policies:
        # 拆分成单IP策略
        single_ip_policies = splitter.split_policy_to_single_ips(
            policy.source_ip or "",
            policy.dest_ip or "",
            policy.service or "",
            policy.action or "permit"
        )

        # 处理每个单IP策略
        for sp in single_ip_policies:
            # 如果不推送，加入不推送列表
            if sp['not_pushed_reason']:
                not_pushed_policies.append({
                    "original_policy_id": policy.id,
                    "source_zone": policy.source_zone,
                    "source_ip": sp['source_ip'],
                    "dest_zone": policy.dest_zone,
                    "dest_ip": sp['dest_ip'],
                    "service": sp['service'],
                    "action": sp['action'],
                    "not_pushed_reason": sp['not_pushed_reason']
                })
                continue

            # 推送的策略：按防火墙分组
            firewall = sp['firewall']
            if firewall.id not in firewall_groups:
                firewall_groups[firewall.id] = {
                    'firewall': firewall,
                    'policies': []
                }

            # 分析NAT
            nat_info = nat_analyzer.analyze_policy(
                sp['source_ip'],
                sp['dest_ip'],
                firewall
            )

            # 边界墙 NAT 透传状态维护
            pass_through = None
            if firewall.is_zone_boundary and nat_info.get("need_nat") and nat_info.get("nat_type") == "SNAT":
                # 入向 NAT（source=external）→ 转换的是源 IP
                # 出向 NAT（source=internal）→ 转换的是目的 IP
                translated_src_ip = nat_info["snat_address"] if nat_info.get("source_zone") == "external" else None
                translated_dst_ip = nat_info["snat_address"] if nat_info.get("source_zone") == "internal" else None
                region_nat_state[firewall.region] = {
                    "translated_src_ip": translated_src_ip,
                    "translated_dst_ip": translated_dst_ip,
                    "source_zone": nat_info.get("source_zone"),
                    "dest_zone": nat_info.get("dest_zone"),
                    "via_firewall": {"id": firewall.id, "name": firewall.name}
                }
            else:
                # 非边界墙：检查同 region 是否有前序边界墙的 NAT 转换
                region_state = region_nat_state.get(firewall.region)
                if region_state and (region_state["translated_src_ip"] or region_state["translated_dst_ip"]):
                    pass_through = {
                        "translated_src_ip": region_state["translated_src_ip"],
                        "translated_dst_ip": region_state["translated_dst_ip"],
                        "source_zone": region_state["source_zone"],
                        "dest_zone": region_state["dest_zone"],
                        "via_firewall": region_state["via_firewall"]
                    }
                    # 关键修正：NAT 已在边界墙上做过，本墙不重复判 SNAT，
                    # 抑制 nat_info.need_nat 避免出现"未配置 SNAT 池"告警
                    nat_info = {
                        **nat_info,
                        "need_nat": False,
                        "nat_type": None,
                        "warnings": [
                            w for w in nat_info.get("warnings", [])
                            if "SNAT地址池" not in w
                        ]
                    }

            # 收集警告
            if nat_info["warnings"]:
                for warning in nat_info["warnings"]:
                    warnings.append(f"策略 {policy.id} ({sp['source_ip']} → {sp['dest_ip']}): {warning}")

            # 添加到分组
            firewall_groups[firewall.id]['policies'].append({
                'original_policy_id': policy.id,
                'source_zone': policy.source_zone,
                'source_ip': sp['source_ip'],
                'dest_zone': policy.dest_zone,
                'dest_ip': sp['dest_ip'],
                'service': sp['service'],
                'action': sp['action'],
                'direction': sp['direction'],
                'nat_info': nat_info,
                'pass_through': pass_through,  # 用于第二步合并后生成 PASS_THROUGH 行
                'original_data': {
                    'source_zone': policy.source_zone,
                    'dest_zone': policy.dest_zone
                }
            })
    
    # 第二步：每个防火墙内执行三步合并
    for firewall_id in firewall_groups:
        policies_to_merge = firewall_groups[firewall_id]['policies']

        # 执行合并
        merged = PolicyMergerV2.merge_policies(policies_to_merge)

        # 添加序号
        for idx, p in enumerate(merged, start=1):
            p['sequence'] = idx
            print(f"DEBUG: 添加序号 {idx} 到策略，当前字段: {list(p.keys())}")

            # 重新生成NAT策略（合并后的）
            if p.get('original_data'):
                nat_info = p.get('nat_info') or nat_analyzer.analyze_policy(
                    p['source_ip'].split('\n')[0],
                    p['dest_ip'].split('\n')[0],
                    firewall_groups[firewall_id]['firewall']
                )
                p['nat_info'] = nat_info
                # 透传信息：合并后第一条的 pass_through 即可（同 region 同一转换）
                pass_through = p.get('pass_through')
                if nat_info.get('need_nat') or pass_through:
                    p['nat_policies'] = _generate_nat_policies(p, nat_info, pass_through=pass_through)
                else:
                    p['nat_policies'] = []

        firewall_groups[firewall_id]['policies'] = merged
    
    # 第三步：为不推送策略添加序号
    for idx, p in enumerate(not_pushed_policies, start=1):
        p['sequence'] = idx
    
    # 转换为列表格式
    firewalls_list = []
    for firewall_id, group in firewall_groups.items():
        firewalls_list.append({
            "firewall_id": group['firewall'].id,
            "firewall_name": group['firewall'].name,
            "firewall": {
                "id": group['firewall'].id,
                "name": group['firewall'].name,
                "alias": group['firewall'].alias,
                "type": group['firewall'].type,
                "management_ip": group['firewall'].management_ip,
                "region": group['firewall'].region,
                "auto_push": group['firewall'].auto_push,
                "push_contact": group['firewall'].push_contact
            },
            "policies": group['policies']
        })
    
    return {
        "order": {
            "id": order.id,
            "order_no": order.order_no,
            "title": order.title,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None
        },
        "firewall_groups": firewalls_list,
        "unmatched_policies": not_pushed_policies,
        "warnings": warnings,
        "errors": errors
    }


def _generate_nat_policies(
    original_policy: Dict,
    nat_info: Dict,
    pass_through: Optional[Dict] = None,
) -> List[Dict]:
    """
    生成 NAT 转换后的策略（SNAT-only）

    项目已决定取消 DNAT 分析, 故只会生成 SNAT 转换行 或 PASS_THROUGH 透传行。

    pass_through: 当本墙不是边界墙但同 region 已有前序边界墙做过 SNAT 时,
                  附加一条 PASS_THROUGH 行（源/目的 IP 替换为 SNAT 后的 IP）
    """
    nat_policies = []

    if nat_info["nat_type"] == "SNAT":
        # SNAT：源IP转换（在本墙做 NAT）
        nat_policies.append({
            "type": "SNAT",
            "source_zone": nat_info["source_zone"],
            "source_ip": nat_info["snat_address"] or "[需要配置SNAT地址]",
            "dest_zone": nat_info["dest_zone"],
            "dest_ip": original_policy["dest_ip"],
            "service": original_policy["service"],
            "action": original_policy["action"]
        })
    # DNAT / BOTH 分支已删除：项目不再分析 DNAT

    # PASS_THROUGH：同 region 其它非边界墙的 SNAT 透传
    if pass_through:
        nat_policies.append({
            "type": "PASS_THROUGH",
            "source_zone": pass_through.get("source_zone", original_policy.get("source_zone")),
            "source_ip": pass_through["translated_src_ip"] or original_policy["source_ip"],
            "dest_zone": pass_through.get("dest_zone", original_policy.get("dest_zone")),
            "dest_ip": pass_through["translated_dst_ip"] or original_policy["dest_ip"],
            "service": original_policy["service"],
            "action": original_policy["action"],
            "via_firewall": pass_through["via_firewall"]
        })

    return nat_policies
