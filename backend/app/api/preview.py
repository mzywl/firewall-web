"""
策略预览API V2 - 完全重写
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
import ipaddress
import logging
from app.database import get_db
from app.models import Order, Policy, Firewall, PolicyVersion, ZoneAccessConfig
from app.core.firewall_matcher import FirewallMatcher, NOT_PUSHED_REASONS
from app.core.nat_analyzer import NATAnalyzer
from app.core.policy_splitter_v2 import PolicySplitterV2, PolicyMergerV2

logger = logging.getLogger(__name__)

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
    matcher = FirewallMatcher(db)   # 用于在 NAT 分析时提供 match_context (区域矩阵 → 设备物理 zone)
    
    # 按防火墙分组
    firewall_groups = {}  # {firewall_id: {'firewall': Firewall, 'policies': []}}
    not_pushed_policies = []  # 不推送的策略
    warnings = []
    errors = []

    # Pass 1+2 级联匹配状态 (D 方案 2026-06-19):
    #   - boundary_snat_map[target_region] = {translated_src_ip, via_firewall, firewall_id}
    #     边界墙 SNAT 转换登记, 给 Pass 2 替换 pending sp 的 src 用
    #   - pending_inbound_sps: fw14 这种 inbound sp, src 命中某个 boundary internal 段,
    #     先暂存, Pass 2 用 SNAT 后 src 重新上墙
    boundary_snat_map: Dict[str, Dict] = {}
    pending_inbound_sps: List[Dict] = []  # [{policy, sp, firewall, match_ctx, via_boundary, original_nat_info}] 

    # 加载 user_modified 快照, 按 policy_id 索引"使用时间"(用户在 Edit 页编辑过的最新值)
    # Policy 表无"使用时间"列, 数据保存在 user_modified 快照里(见 orders.py update_policies)
    usage_time_by_id: dict[int, str] = {}
    user_modified_version = db.query(PolicyVersion).filter(
        PolicyVersion.order_id == order_id,
        PolicyVersion.version_type == 'user_modified'
    ).first()
    if user_modified_version:
        for p_dict in user_modified_version.data.get('policies', []):
            pid = p_dict.get('id')
            ut = p_dict.get('使用时间', '')
            if pid is not None:
                usage_time_by_id[pid] = ut

    # 第一步：拆分所有策略为单IP策略
    for policy in policies:
        # 预计算一次 match_contexts (region 矩阵匹配结果), 在循环内为每个 split 复用
        # 这样 NAT 分析可以直接拿到 device_source_zone / device_dest_zone, 不需要自己再算一次
        try:
            match_contexts = matcher.match_by_policy_context(policy) or []
        except Exception as e:
            logger.warning(f"FirewallMatcher.match_by_policy_context 异常 policy.id={policy.id}: {e}")
            match_contexts = []

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
                    "source_system_name": policy.source_system_name,
                    "source_ip": sp['source_ip'],
                    "dest_system_name": policy.dest_system_name,
                    "dest_ip": sp['dest_ip'],
                    "service": sp['service'],
                    "action": sp['action'],
                    "not_pushed_reason": sp['not_pushed_reason'],
                    "使用时间": usage_time_by_id.get(policy.id, ''),
                })
                continue

            # 防火墙匹配 → NAT 分析 → 上墙 / 暂存 pending
            # D 方案 (Pass 1 + Pass 2 级联匹配):
            #   - boundary fw + SNAT: 登记 SNAT 转换, fw 自己保留原始 src 上墙 (策略匹配在 SNAT 前)
            #   - inbound 方向 + src 命中某个 boundary fw internal 段: 暂存 pending
            #     (本墙物理看不到原始 src, 物理看到的是 SNAT 后 src, Pass 2 替换)
            #   - 其他 (fw outbound, fw 直连 inbound): 直接用原始 src 上墙
            firewall = sp['firewall']
            if firewall.id not in firewall_groups:
                firewall_groups[firewall.id] = {
                    'firewall': firewall,
                    'policies': []
                }

            match_ctx = next(
                (m for m in match_contexts if m.get('firewall_id') == firewall.id),
                None
            )
            nat_info = nat_analyzer.analyze_policy_with_context(
                sp['source_ip'],
                sp['dest_ip'],
                firewall,
                match_context=match_ctx
            )

            # 收集警告
            if nat_info["warnings"]:
                for warning in nat_info["warnings"]:
                    warnings.append(f"策略 {policy.id} ({sp['source_ip']} → {sp['dest_ip']}): {warning}")

            # 情况 1: 边界墙 + SNAT → 登记 SNAT 转换, fw 自己用原始 src 上墙
            if firewall.is_zone_boundary and nat_info.get("need_nat") and nat_info.get("nat_type") == "SNAT":
                translated_src_ip = nat_info["snat_address"]
                # target_region = SNAT 转换后 src 落在的区域, 下游 fw 用它做 key 找转换
                if nat_info.get("source_zone") == "external":
                    # 入向: 转换后 src 进入 fw 的 internal 一侧, 下游 fw (同 covered_region) 看到 src=转换后 IP
                    target_region = firewall.covered_region or firewall.region
                else:
                    # 出向: 转换后 src 落在 fw 的 external 一侧, 下游 fw (对方 covered_region) 看到 src=转换后 IP
                    cfg = db.query(ZoneAccessConfig).filter_by(
                        firewall_id=firewall.id,
                        dest_zone=firewall.external_zone_name
                    ).first()
                    if not cfg:
                        # Fallback 1: zone_name 命名不一致 (e.g. fw.external_zone_name="untrust" vs cfg.dest_zone="生产区"),
                        # 找 source_zone=本墙 covered_region 的 cfg (出向 cfg 的 source = 本墙, dest = 对方)
                        all_cfgs = db.query(ZoneAccessConfig).filter_by(firewall_id=firewall.id).all()
                        own_region = firewall.covered_region or firewall.region
                        for c in all_cfgs:
                            if c.source_zone == own_region:
                                cfg = c
                                break
                        # Fallback 2: substring 匹配 (兼容更复杂的命名不一致)
                        if not cfg:
                            for c in all_cfgs:
                                if (firewall.external_zone_name and firewall.external_zone_name in c.dest_zone) \
                                   or (c.dest_zone and c.dest_zone in firewall.external_zone_name):
                                    cfg = c
                                    break
                    # target_region = 对方 covered_region (出向 SNAT 后 src 进入对方 region)
                    # 找不到 cfg 时不能再 fallback 到 firewall.covered_region (那是同侧, 不是对方!)
                    # → 这种情况 SNAT 转换对下游 fw 无意义, 但仍登记, 由 preview 端排查告警
                    target_region = cfg.dest_zone if cfg else firewall.covered_region or firewall.region

                boundary_snat_map[target_region] = {
                    "translated_src_ip": translated_src_ip,
                    "via_firewall": {"id": firewall.id, "name": firewall.name},
                    "firewall_id": firewall.id,
                }
                # 边界墙自己上墙, src = 原始 IP (策略匹配在 SNAT 转换前)
                firewall_groups[firewall.id]['policies'].append({
                    'original_policy_id': policy.id,
                    'source_system_name': policy.source_system_name,
                    'source_ip': sp['source_ip'],
                    'dest_system_name': policy.dest_system_name,
                    'dest_ip': sp['dest_ip'],
                    'service': sp['service'],
                    'action': sp['action'],
                    'direction': sp['direction'],
                    'nat_info': nat_info,
                    '使用时间': usage_time_by_id.get(policy.id, ''),
                    'original_data': {
                        'source_system_name': policy.source_system_name,
                        'dest_system_name': policy.dest_system_name
                    }
                })
                continue

            # 情况 2: inbound sp → 判定 src 是否需要走 Pass 2 SNAT 透传 (D 方案严格版)
            #   - src 在某 boundary fw 管辖范围 (正向 internal 或反向 external):
            #     暂存 pending, Pass 2 用 boundary fw 对应方向的 SNAT 池替换
            #   - src 不在任何 boundary 管辖范围: 没人 NAT 它 → unmatched
            #     (硬铁律: 防火墙只认当前进到接口的包, 没 SNAT 转换的 src 不能强行上墙)
            if sp['direction'] == 'inbound':
                boundary_match = _find_boundary_fw_for_src(sp['source_ip'], firewall, db)
                if boundary_match:
                    pending_inbound_sps.append({
                        'policy': policy,
                        'sp': sp,
                        'firewall': firewall,
                        'match_ctx': match_ctx,
                        'boundary_match': boundary_match,
                        'original_nat_info': nat_info,
                    })
                else:
                    not_pushed_policies.append({
                        'original_policy_id': policy.id,
                        'source_system_name': policy.source_system_name,
                        'source_ip': sp['source_ip'],
                        'dest_system_name': policy.dest_system_name,
                        'dest_ip': sp['dest_ip'],
                        'service': sp['service'],
                        'action': sp['action'],
                        'not_pushed_reason': f'策略 {policy.id} src={sp["source_ip"]} 不在任何 boundary fw 管辖范围, 无 SNAT 透传可应用',
                        '使用时间': usage_time_by_id.get(policy.id, ''),
                    })
                continue

            # 情况 3: 其他 (fw outbound / fw 直连 inbound) → 直接用原始 src 上墙
            firewall_groups[firewall.id]['policies'].append({
                'original_policy_id': policy.id,
                'source_system_name': policy.source_system_name,
                'source_ip': sp['source_ip'],
                'dest_system_name': policy.dest_system_name,
                'dest_ip': sp['dest_ip'],
                'service': sp['service'],
                'action': sp['action'],
                'direction': sp['direction'],
                'nat_info': nat_info,
                '使用时间': usage_time_by_id.get(policy.id, ''),
                'original_data': {
                    'source_system_name': policy.source_system_name,
                    'dest_system_name': policy.dest_system_name
                }
            })

    # Pass 2: 处理 pending inbound sp, 用 SNAT 后 src 重新上墙
    # 严格按用户级联模型:
    #   - src 在 boundary fw 管辖范围 (正向 internal 或反向 external)
    #     → Pass 2 用 boundary fw 对应方向 SNAT 池替换 src
    #   - src 不在 boundary 范围 (已经在情况 2 直接 unmatched, 不会进 pending)
    for pending in pending_inbound_sps:
        policy = pending['policy']
        sp = pending['sp']
        firewall = pending['firewall']
        match_ctx = pending['match_ctx']
        boundary_match = pending['boundary_match']
        boundary_fw = boundary_match['boundary_fw']

        # key 必须用 下游 fw 的 covered_region (跟 fw6 登记 SNAT 用的 target_region 一致),
        # fw6 SNAT 登记到 boundary_snat_map[对方 region] (cfg.dest_zone),
        # 当前 fw inbound 时应该命中这个 key.
        target_region_key = firewall.covered_region or firewall.region
        snat_info = boundary_snat_map.get(target_region_key)

        if snat_info and snat_info['firewall_id'] != firewall.id:
            # Pass 2: 用 SNAT 后 src 替换, 重算 nat_info
            translated_src = snat_info['translated_src_ip']
            new_nat_info = nat_analyzer.analyze_policy_with_context(
                translated_src,
                sp['dest_ip'],
                firewall,
                match_context=match_ctx
            )
            new_nat_info = {
                **new_nat_info,
                'need_nat': False,
                'nat_type': None,
                'warnings': [w for w in new_nat_info.get('warnings', []) if 'SNAT地址池' not in w],
                'snat_address': translated_src,
                'via_firewall': snat_info['via_firewall'],
            }
            firewall_groups[firewall.id]['policies'].append({
                'original_policy_id': policy.id,
                'source_system_name': policy.source_system_name,
                'source_ip': translated_src,
                'dest_system_name': policy.dest_system_name,
                'dest_ip': sp['dest_ip'],
                'service': sp['service'],
                'action': sp['action'],
                'direction': sp['direction'],
                'nat_info': new_nat_info,
                '使用时间': usage_time_by_id.get(policy.id, ''),
                'original_data': {
                    'source_system_name': policy.source_system_name,
                    'dest_system_name': policy.dest_system_name
                }
            })
        else:
            # Fallback: boundary_match 找到但 SNAT 转换没登记 (e.g. boundary fw 自己的 inbound sp
            # 应该走情况 1, 但万一漏到 pending). 用 boundary_match 自带的 snat_pool 兜底.
            if boundary_match.get('snat_pool') and boundary_match['snat_pool']:
                translated_src = boundary_match['snat_pool']
                new_nat_info = nat_analyzer.analyze_policy_with_context(
                    translated_src,
                    sp['dest_ip'],
                    firewall,
                    match_context=match_ctx
                )
                new_nat_info = {
                    **new_nat_info,
                    'need_nat': False,
                    'nat_type': None,
                    'warnings': [w for w in new_nat_info.get('warnings', []) if 'SNAT地址池' not in w],
                    'snat_address': translated_src,
                    'via_firewall': {'id': boundary_fw.id, 'name': boundary_fw.name},
                }
                firewall_groups[firewall.id]['policies'].append({
                    'original_policy_id': policy.id,
                    'source_system_name': policy.source_system_name,
                    'source_ip': translated_src,
                    'dest_system_name': policy.dest_system_name,
                    'dest_ip': sp['dest_ip'],
                    'service': sp['service'],
                    'action': sp['action'],
                    'direction': sp['direction'],
                    'nat_info': new_nat_info,
                    '使用时间': usage_time_by_id.get(policy.id, ''),
                    'original_data': {
                        'source_system_name': policy.source_system_name,
                        'dest_system_name': policy.dest_system_name
                    }
                })
            else:
                # Fallback 2: boundary fw 没配对应方向 SNAT 池, 没法做 SNAT 透传 → unmatched
                not_pushed_policies.append({
                    'original_policy_id': policy.id,
                    'source_system_name': policy.source_system_name,
                    'source_ip': sp['source_ip'],
                    'dest_system_name': policy.dest_system_name,
                    'dest_ip': sp['dest_ip'],
                    'service': sp['service'],
                    'action': sp['action'],
                    'not_pushed_reason': f'策略 {policy.id} src={sp["source_ip"]} 边界 {boundary_fw.name} 无 {boundary_match["direction"]} SNAT 池配置, 跳过',
                    '使用时间': usage_time_by_id.get(policy.id, ''),
                })

    # 第二步：每个防火墙内执行三步合并
    for firewall_id in firewall_groups:
        policies_to_merge = firewall_groups[firewall_id]['policies']

        # 执行合并
        merged = PolicyMergerV2.merge_policies(policies_to_merge)

        # 添加序号
        for idx, p in enumerate(merged, start=1):
            p['sequence'] = idx

            # 重新生成 NAT 策略行 (合并后, 只 boundary fw 自己生成 SNAT 行)
            # D 方案: 保留 Pass 2 塞进 nat_info 的 snat_address / via_firewall (fw14 的 SNAT 透传标识)
            if p.get('original_data'):
                # 第二阶段 (合并后) 不再能直接拿到原始 match_context, 让 nat_analyzer 走内部降级流即可
                nat_info = p.get('nat_info') or nat_analyzer.analyze_policy_with_context(
                    p['source_ip'].split('\n')[0],
                    p['dest_ip'].split('\n')[0],
                    firewall_groups[firewall_id]['firewall'],
                    match_context=None
                )
                # 保留 Pass 2 塞的 SNAT 透传信息 (D 方案 fw14 的 nat_info.snat_address + via_firewall)
                preserved_snat = p.get('nat_info', {}).get('snat_address')
                preserved_via = p.get('nat_info', {}).get('via_firewall')
                p['nat_info'] = nat_info
                if preserved_snat:
                    p['nat_info']['snat_address'] = preserved_snat
                if preserved_via:
                    p['nat_info']['via_firewall'] = preserved_via
                # 只 boundary fw 自己生成 SNAT 转换行 (后游墙 sp.source_ip 已经是 SNAT 后 IP, 不渲染)
                if nat_info.get('nat_type') == 'SNAT':
                    p['nat_policies'] = _generate_nat_policies(p, nat_info)
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
                "covered_region": group['firewall'].covered_region,
                "local_zone_name": group['firewall'].local_zone_name,
                "external_zone_name": group['firewall'].external_zone_name,
                "is_zone_boundary": group['firewall'].is_zone_boundary,
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
) -> List[Dict]:
    """
    生成 NAT 转换后的策略行（SNAT-only）

    C 方案 (2026-06-19): 简化
    - 项目已决定取消 DNAT 分析, 故只会生成 SNAT 转换行
    - 后游墙 (跨 boundary fw SNAT 透传) 的 sp.source_ip 已被替换成 SNAT 后 IP,
      preview 主循环只对 boundary fw 自己 (nat_info.nat_type=='SNAT') 调用此函数,
      所以这里只生成 SNAT 行, 不再处理 PASS_THROUGH 行 (pass_through 参数已移除)
    """
    nat_policies = []

    if nat_info["nat_type"] == "SNAT":
        # SNAT：源IP转换（在本墙做 NAT）
        nat_policies.append({
            "type": "SNAT",
            "source_zone": nat_info.get("source_zone_name") or nat_info["source_zone"],
            "source_ip": nat_info["snat_address"] or "[需要配置SNAT地址]",
            "dest_zone": nat_info.get("dest_zone_name") or nat_info["dest_zone"],
            "dest_ip": original_policy["dest_ip"],
            "service": original_policy["service"],
            "action": original_policy["action"]
        })
    # DNAT / BOTH 分支已删除：项目不再分析 DNAT
    # PASS_THROUGH 分支已删除 (C 方案): 后游墙 sp.source_ip 直接是 SNAT 后 IP, 不渲染

    return nat_policies


def _find_boundary_fw_for_src(src_ip: str, current_fw: Firewall, db: Session) -> Optional[Dict]:
    """
    找 src_ip 关联的 boundary fw + SNAT 池 (用于 D 方案 Pass 2 透传).

    D 方案严格版: 支持正反向 SNAT 透传.

    业务场景 (按用户级联模型):
      正向访问: src 在 boundary fw internal 段 (src 在 boundary 后面, boundary outbound SNAT)
      反向访问: src 在 boundary fw external 段 (src 在 boundary 前面, boundary inbound SNAT)
      这两种情况下, 当前 fw 物理上看到的 src 应该是 SNAT 后 IP (Pass 2 替换)

    Returns:
      None — 没命中 (sp.src 不在任何 boundary fw 管辖范围)
      {"boundary_fw": Firewall, "snat_pool": str, "direction": "outbound"|"inbound"}
        - snat_pool: 命中的 boundary fw 对应方向的 SNAT 池
        - direction: 该 boundary fw 做的 SNAT 方向 (用于 fw6 区分入/出)
    """
    if not src_ip or src_ip.strip().lower() in ('any', '0.0.0.0'):
        return None
    try:
        src_ip_obj = ipaddress.ip_address(src_ip)
    except ValueError:
        return None

    other_boundary_fws = db.query(Firewall).filter(
        Firewall.id != current_fw.id,
        Firewall.is_zone_boundary == 1,
    ).all()

    for other_fw in other_boundary_fws:
        # 正向: src 在 boundary fw internal 段 (boundary outbound SNAT)
        cidr_text = other_fw.internal_protected_ips or ''
        for line in cidr_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                if src_ip_obj in ipaddress.ip_network(line, strict=False):
                    return {
                        'boundary_fw': other_fw,
                        'snat_pool': other_fw.outbound_snat_pool,
                        'direction': 'outbound',
                    }
            except:
                continue
        # 反向: src 在 boundary fw external 段 (boundary inbound SNAT)
        cidr_text = other_fw.external_protected_ips or ''
        for line in cidr_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                if src_ip_obj in ipaddress.ip_network(line, strict=False):
                    return {
                        'boundary_fw': other_fw,
                        'snat_pool': other_fw.inbound_snat_pool,
                        'direction': 'inbound',
                    }
            except:
                continue
    return None


# _detect_cross_fw_pass_through 已删除 (D 方案 2026-06-19):
# 原函数试图在单遍 splitter + preview 中修补 NAT 透传, 但误把同 region 的前游 fw
# (如 fw7) 当成 boundary fw (fw6) 的下游处理, 把 fw7 的 src 也替换成 SNAT 后 IP.

