"""
策略预览API V2 - chain_planner 重构版

设计对应 backend/重构.md §6.2 "拓扑寻路与 NAT 链式预分析":
  - 本路由只负责"按 firewall 分组 + 合并 + NAT 行渲染 + JSON 响应"
  - 链式寻路 + NAT 透传决策委托给 app.core.chain_planner
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
import logging

from app.database import get_db
from app.models import Order, Policy, PolicyVersion
from app.core.chain_planner import ChainPlanner
from app.core.nat_analyzer import NATAnalyzer
from app.core.policy_splitter_v2 import PolicyMergerV2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workorders", tags=["preview"])


@router.get("/{order_id}/preview")
def get_preview_data(order_id: int, db: Session = Depends(get_db)):
    """
    获取策略预览数据 V2 (chain_planner 重构版)

    流水线:
      1. 加载工单 + 策略 + user_modified 快照
      2. ChainPlanner.generate_chain_execution_plan() → ChainContext
         (含按 firewall 分组的 sp + pending + warnings)
      3. 每个防火墙内执行 PolicyMergerV2 三步合并
      4. 渲染 NAT 行 (仅 boundary fw 自己)
      5. 拼 JSON 响应
    """
    # 加载工单
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    # 加载策略
    policies = db.query(Policy).filter(Policy.order_id == order_id).all()

    # 加载 user_modified 快照, 按 policy_id 索引"使用时间"
    # Policy 表无"使用时间"列, 数据保存在 user_modified 快照里 (见 orders.py update_policies)
    usage_time_by_id: dict[int, str] = {}
    user_modified_version = (
        db.query(PolicyVersion)
        .filter(
            PolicyVersion.order_id == order_id,
            PolicyVersion.version_type == "user_modified",
        )
        .first()
    )
    if user_modified_version:
        for p_dict in user_modified_version.data.get("policies", []):
            pid = p_dict.get("id")
            ut = p_dict.get("使用时间", "")
            if pid is not None:
                usage_time_by_id[pid] = ut

    # 1. 链式寻路: Pass 1 + Pass 2 级联匹配
    planner = ChainPlanner(db)
    ctx = planner.generate_chain_execution_plan(policies, usage_time_by_id)

    # 2. 每个防火墙内执行三步合并 + NAT 行渲染
    nat_analyzer = NATAnalyzer(db)
    for firewall_id, group in ctx.firewall_groups.items():
        merged = PolicyMergerV2.merge_policies(group["policies"])
        for idx, p in enumerate(merged, start=1):
            p["sequence"] = idx
            p["nat_policies"] = _build_nat_policies(p, group["firewall"], nat_analyzer)
        group["policies"] = merged

    # 3. 为不推送策略添加序号
    for idx, p in enumerate(ctx.not_pushed, start=1):
        p["sequence"] = idx

    # 4. 拼 JSON 响应
    firewalls_list = [
        {
            "firewall_id": group["firewall"].id,
            "firewall_name": group["firewall"].name,
            "firewall": {
                "id": group["firewall"].id,
                "name": group["firewall"].name,
                "alias": group["firewall"].alias,
                "type": group["firewall"].type,
                "management_ip": group["firewall"].management_ip,
                # 新设计 (2026-06-22): covered_region/local_zone_name/external_zone_name/push_contact 已删除
                "belong_region": group["firewall"].belong_region,
                # 2026-06-22: 前端用 is_zone_boundary 加 "将在此墙推送" 标识
                "is_zone_boundary": group["firewall"].is_zone_boundary,
                "auto_push": group["firewall"].auto_push,
            },
            "policies": group["policies"],
        }
        for group in ctx.firewall_groups.values()
    ]

    return {
        "order": {
            "id": order.id,
            "order_no": order.order_no,
            "title": order.title,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
        "firewall_groups": firewalls_list,
        "unmatched_policies": ctx.not_pushed,
        "warnings": ctx.warnings,
        "errors": [],
    }


def _build_nat_policies(
    merged_policy: Dict,
    firewall,
    nat_analyzer: NATAnalyzer,
) -> List[Dict]:
    """
    渲染 NAT 转换行 (SNAT 透传 + 自身 SNAT)

    2026-06-22 重构: 区分两种 SNAT 行
      - "SNAT": boundary fw 自己转换 (蓝行)
      - "PASS_THROUGH": 下游 fw 被上游 boundary SNAT 透传 (绿行, 显示原 src IP)
    """
    if not merged_policy.get("original_data"):
        return []

    rows = []

    # 情形 1: Pass 2 SNAT 透传 (D 方案) — merged_policy.nat_info 里有 via_firewall + snat_address
    nat_info = merged_policy.get("nat_info") or {}
    if nat_info.get("via_firewall") and nat_info.get("snat_address"):
        via = nat_info["via_firewall"]
        original_src = merged_policy.get("original_source_ip", merged_policy["source_ip"])
        rows.append({
            "type": "PASS_THROUGH",
            "source_zone": merged_policy.get("source_system_name") or "-",
            "source_ip": nat_info["snat_address"],  # 透传后 src (上游 boundary SNAT 后)
            "dest_zone": merged_policy.get("dest_system_name") or "-",
            "dest_ip": merged_policy["dest_ip"],
            "service": merged_policy["service"],
            "action": merged_policy.get("action", "permit"),
            "via_firewall": via,
            "original_source_ip": original_src,  # 2026-06-22 透传原 IP 给前端展示
        })

    # 情形 2: boundary fw 自身需要 SNAT 转换 (蓝行, 显示转换后 src)
    nat_info_for_self = nat_analyzer.analyze_policy_with_context(
        merged_policy["source_ip"].split("\n")[0],
        merged_policy["dest_ip"].split("\n")[0],
        firewall,
        match_context=None,
    )
    # 保留 Pass 2 塞的 SNAT 透传信息 (即使自身不需要 SNAT 也要透传这俩字段给前端)
    merged_policy["nat_info"] = nat_info_for_self
    if nat_info.get("snat_address"):
        merged_policy["nat_info"]["snat_address"] = nat_info["snat_address"]
    if nat_info.get("via_firewall"):
        merged_policy["nat_info"]["via_firewall"] = nat_info["via_firewall"]

    if nat_info_for_self.get("nat_type") == "SNAT" and not rows:
        rows.extend(_generate_snat_row(merged_policy, nat_info_for_self))

    return rows


# 向后兼容别名 (test_merger_pass_through_list 等老测试用旧名)
_generate_nat_policies = _build_nat_policies


def _generate_snat_row(
    original_policy: Dict,
    nat_info: Dict,
) -> List[Dict]:
    """
    生成 SNAT 转换行 (源 IP 转换)

    铁律: SNAT 永远换 src IP (不管入向出向), dst 不变
    """
    return [
        {
            "type": "SNAT",
            "source_zone": nat_info.get("source_zone_name") or nat_info["source_zone"],
            "source_ip": nat_info["snat_address"] or "[需要配置SNAT地址]",
            "dest_zone": nat_info.get("dest_zone_name") or nat_info["dest_zone"],
            "dest_ip": original_policy["dest_ip"],
            "service": original_policy["service"],
            "action": original_policy["action"],
        }
    ]
