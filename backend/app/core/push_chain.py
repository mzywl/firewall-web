"""
推送链路排序工具 (重构.md §4 倒序下发铁律)

铁律: 跨防火墙推送必须倒序串行 (目的端墙 → 边界墙 → 源端墙),
原因: 边界墙 SNAT 配置生效瞬间, 流量会立即打向后游墙, 后游墙未配
则触发默认拒绝策略, 监控大屏告警. 倒序保证"后游墙静默等待, 边界墙
NAT 就绪, 源端墙开闸放行".

当前 V2 推送架构: 每次只推一墙 (per firewall_id), 不循环. 倒序逻辑
由调用方 (前端 / V3 chain 模式) 决定, 本模块只暴露拓扑信息工具.

compute_push_chain(order_id, db) → List[int]:
  返回该工单涉及的防火墙 ID, 按推送顺序排列:
  1. 非边界 + inbound sp 被 boundary 触发 SNAT 透传的墙 (后游 / 目的端)
  2. 边界墙 (is_zone_boundary=1, 做 SNAT)
  3. 非边界 + outbound / 直连 inbound 墙 (前游 / 源端)

设计取舍:
  - 只按当前工单 policy 涉及的防火墙计算, 不依赖 firewall_groups 排序
  - 用 ChainPlanner 跑一次拿到 boundary_snat_map + pending_inbound_sps
  - 从 boundary_snat_map 反推后游墙 (covered_region 命中 key)
  - 边界墙自己最后推 (在中间层)
  - 前游墙最后推 (流量起点)
"""
from typing import Dict, List, Set

from sqlalchemy.orm import Session

from app.core.chain_planner import ChainPlanner
from app.models import Firewall, Order, Policy


def compute_push_chain(order_id: int, db: Session) -> List[int]:
    """
    计算工单多墙推送的倒序防火墙 ID 列表.

    顺序: [后游墙 (目的端), 边界墙 (中间), 前游墙 (源端)]
    (这是"倒序" — 跟流量方向 src→dst 反着推)

    Args:
        order_id: 工单 ID
        db: SQLAlchemy Session

    Returns:
        防火墙 ID 列表, 按推送顺序排列. 涉及 N 台防火墙就返回 N 个 ID.
        1 台墙时仍按规则排序 (保证可预测性).
        工单无策略时返回 [].

    Example:
        工单 28 涉及 3 墙: fw6 (boundary) + fw7 (前游 outbound) + fw14 (后游 inbound)
        → compute_push_chain(28, db) → [14, 6, 7]
        推送顺序: 先配 fw14 (目的端, 静默等待 SNAT 后流量) → fw6 (SNAT 生效)
        → fw7 (源端, 流量开始通过)
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return []

    policies: List[Policy] = order.policies
    if not policies:
        return []

    # 用 ChainPlanner 跑一次, 拿到 boundary_snat_map (后游墙识别用)
    planner = ChainPlanner(db)
    # usage_time_by_id 留空 (本函数不需要)
    ctx = planner.generate_chain_execution_plan(policies, {})

    # 分类三组防火墙
    downstream_fw_ids: Set[int] = set()  # 后游 (目的端)
    boundary_fw_ids: Set[int] = set()    # 边界 (中间, 做 SNAT)
    upstream_fw_ids: Set[int] = set()    # 前游 (源端)

    # 1) 边界墙: 从 boundary_snat_map 的 via_firewall.firewall_id 拿
    for target_region, snat_info in ctx.boundary_snat_map.items():
        boundary_fw_ids.add(snat_info["firewall_id"])

    # 2) 后游墙: pending_inbound_sps 的 firewall (inbound 方向, src 被 boundary 接管)
    for pending in ctx.pending_inbound_sps:
        downstream_fw_ids.add(pending["firewall"].id)

    # 3) 前游墙: ctx.firewall_groups 里有 sp 但不在前两组里的 (outbound 或直连 inbound)
    all_fw_ids: Set[int] = set(ctx.firewall_groups.keys())
    for fw_id in all_fw_ids:
        if fw_id in boundary_fw_ids or fw_id in downstream_fw_ids:
            continue
        upstream_fw_ids.add(fw_id)

    # 倒序拼接: 后游 → 边界 → 前游
    # 同组内按 ID 升序 (确定性强, 方便测试)
    push_chain: List[int] = (
        sorted(downstream_fw_ids)
        + sorted(boundary_fw_ids)
        + sorted(upstream_fw_ids)
    )

    return push_chain


def get_push_chain_with_metadata(order_id: int, db: Session) -> List[Dict]:
    """
    带元数据的倒序推送链 (给前端 UI 用, 显示 "先推 fw14, 再推 fw6, 再推 fw7" 这种步骤条).

    Returns:
        [
          {"firewall_id": 14, "name": "fw14", "role": "downstream",
           "reason": "目的端墙, inbound 方向, src 由 fw6 SNAT 接管"},
          {"firewall_id": 6,  "name": "fw6",  "role": "boundary",
           "reason": "边界防火墙, 做 SNAT 转换"},
          {"firewall_id": 7,  "name": "fw7",  "role": "upstream",
           "reason": "源端墙, outbound 方向, 流量起点"},
          ...
        ]
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return []

    policies: List[Policy] = order.policies
    if not policies:
        return []

    planner = ChainPlanner(db)
    ctx = planner.generate_chain_execution_plan(policies, {})

    # 分类
    downstream_fw_ids: Set[int] = set()
    boundary_fw_ids: Set[int] = set()
    upstream_fw_ids: Set[int] = set()

    for target_region, snat_info in ctx.boundary_snat_map.items():
        boundary_fw_ids.add(snat_info["firewall_id"])
    for pending in ctx.pending_inbound_sps:
        downstream_fw_ids.add(pending["firewall"].id)
    for fw_id in set(ctx.firewall_groups.keys()):
        if fw_id not in boundary_fw_ids and fw_id not in downstream_fw_ids:
            upstream_fw_ids.add(fw_id)

    # 加载 firewall 元数据
    all_ids = downstream_fw_ids | boundary_fw_ids | upstream_fw_ids
    firewalls = {
        fw.id: fw
        for fw in db.query(Firewall).filter(Firewall.id.in_(all_ids)).all()
    }

    # 拼结果
    result: List[Dict] = []
    for fw_id in sorted(downstream_fw_ids):
        fw = firewalls.get(fw_id)
        result.append({
            "firewall_id": fw_id,
            "name": fw.name if fw else f"fw-{fw_id}",
            "role": "downstream",
            "reason": "目的端墙, inbound 方向, src 由边界防火墙 SNAT 接管",
        })
    for fw_id in sorted(boundary_fw_ids):
        fw = firewalls.get(fw_id)
        result.append({
            "firewall_id": fw_id,
            "name": fw.name if fw else f"fw-{fw_id}",
            "role": "boundary",
            "reason": "边界防火墙, 做 SNAT 转换",
        })
    for fw_id in sorted(upstream_fw_ids):
        fw = firewalls.get(fw_id)
        result.append({
            "firewall_id": fw_id,
            "name": fw.name if fw else f"fw-{fw_id}",
            "role": "upstream",
            "reason": "源端墙, outbound 方向, 流量起点",
        })

    return result
