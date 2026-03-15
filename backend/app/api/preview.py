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
    
    # 按防火墙分组
    firewall_groups = {}
    not_pushed_policies = []
    warnings = []
    errors = []
    
    for policy in policies:
        # 使用新的多防火墙匹配逻辑
        matched_firewalls = matcher.match_firewalls_by_policy(
            policy.source_ip or "",
            policy.dest_ip or ""
        )
        
        # 如果没有匹配到任何防火墙
        if not matched_firewalls:
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
        
        # 遍历所有匹配的防火墙
        for match in matched_firewalls:
            firewall = match['firewall']
            source_match = match['source_match']
            dest_match = match['dest_match']
            
            # 判断是否应该推送（同墙策略检查）
            should_push, not_push_reason = matcher.should_push_same_firewall_policy(
                firewall, source_match, dest_match
            )
            
            if not should_push:
                # 不推送的策略
                not_pushed_policies.append({
                    "id": policy.id,
                    "source_zone": policy.source_zone,
                    "source_ip": policy.source_ip,
                    "dest_zone": policy.dest_zone,
                    "dest_ip": policy.dest_ip,
                    "service": policy.service,
                    "action": policy.action,
                    "not_pushed_reason": not_push_reason
                })
                continue
            
            # 分析NAT需求
            nat_info = nat_analyzer.analyze_policy(
                policy.source_ip or "",
                policy.dest_ip or "",
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
                "source_ip": policy.source_ip,
                "dest_zone": policy.dest_zone,
                "dest_ip": policy.dest_ip,
                "service": policy.service,
                "action": policy.action,
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
    
    # 转换为列表
    firewalls_list = list(firewall_groups.values())
    
    return {
        "order": {
            "id": order.id,
            "order_no": order.order_no,
            "title": order.title,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None
        },
        "firewalls": firewalls_list,
        "not_pushed_policies": not_pushed_policies,
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
