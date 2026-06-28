"""
策略预览API V2 - chain_planner 重构版

设计对应 backend/重构.md §6.2 "拓扑寻路与 NAT 链式预分析":
  - 本路由只负责"按 firewall 分组 + 合并 + NAT 行渲染 + JSON 响应"
  - 链式寻路 + NAT 透传决策委托给 app.core.chain_planner
"""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict
import logging

from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.models import Order, Policy, PolicyVersion, OrderStatus
from app.core.chain_planner import ChainPlanner
from app.core.nat_analyzer import NATAnalyzer
from app.core.policy_splitter_v2 import PolicyMergerV2
from app.schemas import  IgnorePlanRowRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workorders", tags=["preview"])


@router.get("/{order_id}/preview")
def get_preview_data(order_id: int, force_rebuild: bool = False, db: Session = Depends(get_db)):
    """
    获取策略预览数据：
    优先读取 user_modified → formatted_v2
    不再兜底读取 Policy 表
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    # 1. 如果已有执行计划且不强制重建，直接返回
    plan_version = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == "execution_plan"
    ).first()

    if plan_version and plan_version.data and not force_rebuild:
        return plan_version.data

    # 2. 优先 user_modified → formatted_v2
    snapshot_data = None
    used_version = None

    # 优先 user_modified
    user_modified = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == "user_modified"
    ).first()

    if user_modified and user_modified.data and user_modified.data.get("policies"):
        snapshot_data = user_modified.data["policies"]
        used_version = "user_modified"

    # 其次 formatted_v2
    if snapshot_data is None:
        formatted_v2 = db.query(PolicyVersion).filter(
            PolicyVersion.order_id == order_id,
            PolicyVersion.version_type == "formatted_v2"
        ).first()
        if formatted_v2 and formatted_v2.data and formatted_v2.data.get("policies"):
            snapshot_data = formatted_v2.data["policies"]
            used_version = "formatted_v2"
    if snapshot_data is None:
        raise HTTPException(status_code=400, detail="无可用策略数据（缺少 user_modified 或 formatted_v2）")

    # 3. 转换为 Policy 对象用于执行计划计算
    policies_to_plan = []
    usage_time_by_id = {}

    for p_dict in snapshot_data:
        p_id = p_dict.get("id")
        if p_id:
            usage_time_by_id[p_id] = p_dict.get("使用时间") or ""

        temp_policy = Policy(
            id=p_id,
            order_id=order_id,
            source_system_name=p_dict.get("源端系统-环境-用途"),
            source_ip=p_dict.get("源IP"),
            device_source_zone=p_dict.get("源安全域"),
            dest_system_name=p_dict.get("目的端系统-环境-用途"),
            dest_ip=p_dict.get("目的IP"),
            device_dest_zone=p_dict.get("目的安全域"),
            service=p_dict.get("目的端口"),
            usage_time=usage_time_by_id.get(p_id, "")
        )
        policies_to_plan.append(temp_policy)

    # 4. 执行计划计算
    planner = ChainPlanner(db)
    ctx = planner.generate_chain_execution_plan(policies_to_plan, usage_time_by_id)
    nat_analyzer = NATAnalyzer(db)

    # 5. 构建渲染数据（带 UUID）
    firewalls_list = []
    for firewall_id, group in ctx.firewall_groups.items():
        merged = PolicyMergerV2.merge_policies(group["policies"])
        for idx, p in enumerate(merged, start=1):
            p["sequence"] = idx
            p["row_uuid"] = str(uuid.uuid4())
            p["is_ignored"] = False
            p["nat_policies"] = _build_nat_policies(p, group["firewall"], nat_analyzer)

        firewalls_list.append({
            "firewall_id": group["firewall"].id,
            "firewall_name": group["firewall"].name,
            "firewall": {
                "id": group["firewall"].id,
                "name": group["firewall"].name,
                "alias": group["firewall"].alias,
                "type": group["firewall"].type,
                "management_ip": group["firewall"].management_ip,
                "belong_region": group["firewall"].belong_region,
                "is_zone_boundary": group["firewall"].is_zone_boundary,
                "auto_push": group["firewall"].auto_push,
            },
            "policies": merged,
        })

    for idx, p in enumerate(ctx.not_pushed, start=1):
        p["sequence"] = idx
        p["row_uuid"] = str(uuid.uuid4())

    plan_data = {
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
        "used_version": used_version,
    }

    # 6. 保存执行计划
    if not plan_version:
        plan_version = PolicyVersion(order_id=order_id, version_type="execution_plan", data=plan_data)
        db.add(plan_version)
    else:
        plan_version.data = plan_data
        flag_modified(plan_version, "data")

    db.commit()
    return plan_data


import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.database import get_db
from app.models import Order, Policy, PolicyVersion, OrderStatus

logger = logging.getLogger(__name__)


@router.post("/{order_id}/commit")
def commit_order_policies(order_id: int, db: Session = Depends(get_db)):
    """
    提交工单：将执行计划快照写入 policies 物理表。
    安全策略IP原样写入，仅针对边界墙额外生成 NAT 映射关系。
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    plan_version = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == "execution_plan"
    ).first()

    if not plan_version or not plan_version.data:
        raise HTTPException(status_code=400, detail="未找到执行计划，请先前往预览页检查策略。")

    plan_data = plan_version.data

    if plan_data.get("unmatched_policies"):
        raise HTTPException(status_code=400, detail="存在未匹配防火墙的策略，无法提交，请先修改源/目的IP。")

    try:
        # 清除历史脏记录
        db.query(Policy).filter(Policy.order_id == order_id).delete()
        policies_to_insert = []

        # 遍历执行计划中的每一个防火墙
        for fw_group in plan_data.get("firewall_groups", []):
            fw_id = fw_group["firewall_id"]

            for p_dict in fw_group.get("policies", []):

                # 1. 直接读取执行计划中算好的 source_ip，坚决不篡改！
                final_source_ip = str(p_dict.get("source_ip", ""))
                source_snat_mapping = None

                nat_info = p_dict.get("nat_info") or {}

                # 2. 只有当前墙是真正的【边界墙】（执行 SNAT）时，才写入映射关系
                if nat_info.get("nat_type") == "SNAT" and nat_info.get("snat_address"):
                    snat_address = nat_info.get("snat_address")

                    # 为了映射的准确性，优先取 original_source_ip，没有则取 final_source_ip
                    original_ip_for_mapping = p_dict.get("original_source_ip") or final_source_ip

                    mappings = []
                    # 按换行符或逗号切割多个 IP
                    ip_list = [ip.strip() for ip in re.split(r'[\n,]', original_ip_for_mapping) if ip.strip()]

                    # 组装关系：原IP-->NAT地址
                    for ip in ip_list:
                        mappings.append(f"{ip}-->{snat_address}")

                    source_snat_mapping = "\n".join(mappings) if mappings else None

                # 获取前端打的忽略（软删除）标记
                is_ignored = p_dict.get("is_ignored", False)
                final_push_status = "ignored" if is_ignored else "pending"

                new_policy = Policy(
                    order_id=order_id,
                    firewall_id=fw_id,
                    source_system_name=p_dict.get("source_system_name"),
                    dest_system_name=p_dict.get("dest_system_name"),

                    # 写入数据库（安全策略IP 与 NAT映射 分离）
                    source_ip=final_source_ip,
                    source_snat_ip=source_snat_mapping,

                    dest_ip=p_dict.get("dest_ip"),
                    service=p_dict.get("service"),
                    device_source_zone=p_dict.get("device_source_zone") or p_dict.get("src_zone_name") or "Untrust",
                    device_dest_zone=p_dict.get("device_dest_zone") or p_dict.get("dst_zone_name") or "Trust",
                    usage_time=p_dict.get("usage_time", ""),
                    push_status=final_push_status,
                    created_at=datetime.now()
                )
                policies_to_insert.append(new_policy)

        if policies_to_insert:
            db.add_all(policies_to_insert)

        # 推进工单状态
        if hasattr(OrderStatus, 'pending_push'):
            order.status = OrderStatus.pending_push

        db.commit()

        return {
            "message": "执行计划已成功入库",
            "inserted_count": len(policies_to_insert)
        }

    except Exception as e:
        db.rollback()
        logger.error(f"工单 {order_id} 策略入库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"数据入库失败: {str(e)}")
@router.put("/{order_id}/plan/ignore")
def toggle_plan_row_ignore(order_id: int, req: IgnorePlanRowRequest, db: Session = Depends(get_db)):
    """
    修改执行计划：根据前端传递的 row_uuid 软删除或恢复对应的策略行
    """
    plan_version = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == "execution_plan"
    ).first()

    if not plan_version or not plan_version.data:
        raise HTTPException(status_code=404, detail="执行计划不存在，请先前往预览页生成策略。")

    data = plan_version.data
    row_found = False

    # 遍历防火墙大组，找到对应的 uuid 修改状态
    for fw_group in data.get("firewall_groups", []):
        for p in fw_group.get("policies", []):
            if p.get("row_uuid") == req.row_uuid:
                p["is_ignored"] = req.ignore
                row_found = True
                break
        if row_found:
            break

    if not row_found:
        raise HTTPException(status_code=404, detail="未找到对应的策略行，请刷新页面重试。")

    # 标记 JSON 脏数据，保存修改
    flag_modified(plan_version, "data")
    db.commit()

    return {"message": "状态已更新", "row_uuid": req.row_uuid, "is_ignored": req.ignore}

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
