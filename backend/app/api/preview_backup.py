"""
策略预览API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from app.database import get_db
from app.models import Order, Policy, Firewall
from app.core.firewall_matcher import FirewallMatcher, NOT_PUSHED_REASONS
from app.core.nat_analyzer import NATAnalyzer
from app.core.policy_splitter import PolicySplitter, PolicyMerger

router = APIRouter(prefix="/api/workorders", tags=["preview"])


@router.get("/{order_id}/preview")
def get_preview_data(order_id: int, db: Session = Depends(get_db)):
    """
    获取策略预览数据
    
    返回格式：
    {
        "order": {...},
        "firewalls": [
            {
                "firewall_id": 1,
                "firewall_name": "云防火墙",
                "policies": [...]
            }
        ],
        "not_pushed_policies": [
            {
                "id": 123,
                "source_ip": "...",
                "dest_ip": "...",
                "not_pushed_reason": "..."
            }
        ],
        "warnings": [...],
        "errors": [...]
    }
    """
    # 查询工单
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    
    # 查询所有策略
    policies = db.query(Policy).filter(Policy.order_id == order_id).all()
    
    # 初始化分析器
    matcher = FirewallMatcher(db)
    nat_analyzer = NATAnalyzer(db)
    splitter = PolicySplitter(db)
    
    # 按防火墙分组（用于拆分后的策略）
    firewall_groups = {}
    not_pushed_policies = []
    warnings = []
    errors = []
    
    for policy in policies:
        # 拆分源地址和目的地址（按换行符）
        source_ips = [ip.strip() for ip in (policy.source_ip or "").split('\n') if ip.strip()]
        dest_ips = [ip.strip() for ip in (policy.dest_ip or "").split('\n') if ip.strip()]
        
        # 使用策略拆分器：一行策略可能拆分成多个防火墙的多条策略
        split_policies = splitter.split_policy(
            source_ips, dest_ips, 
            policy.service or "", 
            policy.action or "permit"
        )
        
        # 如果没有匹配到任何防火墙
        if not split_policies:
            not_pushed_policies.append({
                "id": policy.id,
                "source_zone": policy.source_zone,
                "source_ip": policy.source_ip,
                "dest_zone": policy.dest_zone,
                "dest_ip": policy.dest_ip,
                "service": policy.service,
                "action": policy.action,
                "not_pushed_reason": NOT_PUSHED_REASONS['NO_FIREWALL_MATCH']
            })
            continue
        
        # 遍历拆分后的策略
        for split_policy in split_policies:
            firewall = split_policy['firewall']
            direction = split_policy['direction']
            
            # 判断是否应该推送（同墙策略检查）
            should_push, not_push_reason = matcher.should_push_same_firewall_policy(
                firewall, direction
            )
            
            if not should_push:
                # 不推送的策略
                not_pushed_policies.append({
                    "id": policy.id,
                    "source_zone": policy.source_zone,
                    "source_ip": '\n'.join(split_policy['source_ips']),
                    "dest_zone": policy.dest_zone,
                    "dest_ip": '\n'.join(split_policy['dest_ips']),
                    "service": split_policy['service'],
                    "action": split_policy['action'],
                    "not_pushed_reason": not_push_reason
                })
                continue
            
            # 分析NAT需求（使用拆分后的第一个IP）
            first_source = split_policy['source_ips'][0] if split_policy['source_ips'] else ""
            first_dest = split_policy['dest_ips'][0] if split_policy['dest_ips'] else ""
            nat_info = nat_analyzer.analyze_policy(
                first_source,
                first_dest,
                firewall
            )
            
            # 收集警告
            if nat_info["warnings"]:
                for warning in nat_info["warnings"]:
                    warnings.append(f"策略 {policy.id}: {warning}")
            
            # 构建策略数据
            policy_data = {
                "id": policy.id,
                "source_zone": policy.source_zone,
                "source_ip": '\n'.join(split_policy['source_ips']),
                "dest_zone": policy.dest_zone,
                "dest_ip": '\n'.join(split_policy['dest_ips']),
                "service": split_policy['service'],
                "action": split_policy['action'],
                "direction": direction,
                "nat_info": nat_info,
                "nat_policies": []
            }
            
            # 生成NAT转换后的策略
            if nat_info["need_nat"]:
                nat_policies = _generate_nat_policies(policy_data, nat_info)
                policy_data["nat_policies"] = nat_policies
            
            # 添加到防火墙分组
            firewall_id = firewall.id
            if firewall_id not in firewall_groups:
                firewall_groups[firewall_id] = {
                    "firewall_id": firewall.id,
                    "firewall_name": firewall.name,
                    "firewall": {
                        "id": firewall.id,
                        "name": firewall.name,
                        "alias": firewall.alias,
                        "type": firewall.type,
                        "management_ip": firewall.management_ip,
                        "region": firewall.region,
                        "auto_push": firewall.auto_push,
                        "push_contact": firewall.push_contact
                    },
                    "policies": []
                }
            
            firewall_groups[firewall_id]["policies"].append(policy_data)
    
    # 对每个防火墙的策略进行合并
    for firewall_id in firewall_groups:
        # 转换为合并器需要的格式
        policies_to_merge = []
        for p in firewall_groups[firewall_id]["policies"]:
            policies_to_merge.append({
                'source_ips': p['source_ip'].split('\n'),
                'dest_ips': p['dest_ip'].split('\n'),
                'service': p['service'],
                'action': p['action'],
                'original_data': p  # 保留原始数据
            })
        
        # 执行三步合并
        merged = PolicyMerger.merge_policies(policies_to_merge)
        
        # 转换回显示格式并添加序号
        merged_policies = []
        for idx, m in enumerate(merged, start=1):
            original = m['original_data']
            original['source_ip'] = '\n'.join(m['source_ips'])
            original['dest_ip'] = '\n'.join(m['dest_ips'])
            original['service'] = m['service']
            original['sequence'] = idx  # 添加序号
            merged_policies.append(original)
        
        firewall_groups[firewall_id]["policies"] = merged_policies
    
    # 转换为列表
    firewalls_list = list(firewall_groups.values())
    
    # 为未匹配策略添加序号
    for idx, p in enumerate(not_pushed_policies, start=1):
        p['sequence'] = idx
    
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


def _generate_nat_policies(original_policy: Dict, nat_info: Dict) -> List[Dict]:
    """
    生成NAT转换后的策略
    """
    nat_policies = []
    
    if nat_info["nat_type"] == "SNAT":
        # SNAT：源IP转换
        nat_policies.append({
            "type": "SNAT",
            "source_zone": nat_info["source_zone"],
            "source_ip": nat_info["snat_address"] or "[需要配置SNAT地址]",
            "dest_zone": nat_info["dest_zone"],
            "dest_ip": original_policy["dest_ip"],
            "service": original_policy["service"],
            "action": original_policy["action"]
        })
    
    elif nat_info["nat_type"] == "DNAT":
        # DNAT：目的IP转换
        nat_policies.append({
            "type": "DNAT",
            "source_zone": nat_info["source_zone"],
            "source_ip": original_policy["source_ip"],
            "dest_zone": nat_info["dest_zone"],
            "dest_ip": nat_info["dnat_address"] or "[需要配置DNAT地址]",
            "service": original_policy["service"],
            "action": original_policy["action"]
        })
    
    elif nat_info["nat_type"] == "BOTH":
        # 双向NAT：先SNAT，再DNAT
        nat_policies.append({
            "type": "SNAT",
            "source_zone": nat_info["source_zone"],
            "source_ip": nat_info["snat_address"] or "[需要配置SNAT地址]",
            "dest_zone": nat_info["dest_zone"],
            "dest_ip": original_policy["dest_ip"],
            "service": original_policy["service"],
            "action": original_policy["action"]
        })
        nat_policies.append({
            "type": "DNAT",
            "source_zone": nat_info["source_zone"],
            "source_ip": nat_info["snat_address"] or "[需要配置SNAT地址]",
            "dest_zone": nat_info["dest_zone"],
            "dest_ip": nat_info["dnat_address"] or "[需要配置DNAT地址]",
            "service": original_policy["service"],
            "action": original_policy["action"]
        })
    
    return nat_policies
