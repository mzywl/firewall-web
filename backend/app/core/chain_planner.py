"""
链式寻路 + NAT 透传规划器 (chain_planner)

封装 firewall_matcher + nat_analyzer + splitter_v2 的物理拓扑逻辑,提供
generate_chain_execution_plan() 单一入口。设计对应 backend/重构.md §2
"链式寻路算法与 NAT 动态重写"。

核心铁律 (任何重构不能违反):
  1. 防火墙只认当前进到它接口里的数据包
  2. 策略匹配在 SNAT 转换前
  3. (direction, src 归属) 二元判定 fw 是 boundary 上游还是下游 (SKILL 坑点 33)

D 方案 (2026-06-19) Pass 1+Pass 2 级联匹配:
  - Pass 1: 用原始 src 跑 splitter,边界墙 + SNAT 时登记 boundary_snat_map,
            边界墙自己保留原始 src 上墙 (策略匹配在 SNAT 前)
  - Pass 2: pending inbound sp (src 命中 boundary internal 段) 用 SNAT 后
            src 替换,重算 nat_info,重新上墙

本模块不负责:
  - merger 合并 (policy_splitter_v2.PolicyMergerV2)
  - NAT 行渲染 (preview._generate_nat_policies)
  - JSON 响应拼装 (preview.get_preview_data)
"""
from typing import Dict, List, Optional, Any
import ipaddress
import logging

from sqlalchemy.orm import Session

from app.models import Firewall, Policy, ZoneAccessConfig
from app.core.firewall_matcher import FirewallMatcher
from app.core.nat_analyzer import NATAnalyzer
from app.core.policy_splitter_v2 import PolicySplitterV2

logger = logging.getLogger(__name__)


# ============================================================
# 链式寻路共享状态 (D 方案 Pass 1+Pass 2 必需)
# ============================================================
class ChainContext:
    """
    跨 policy 共享的级联匹配状态。

    设计要点:
    - boundary_snat_map: 边界墙 SNAT 转换登记, key = target_region,
        value = {translated_src_ip, via_firewall, firewall_id}
    - pending_inbound_sps: 暂存待 Pass 2 替换 src 的 inbound sp
        (物理上 fw 看不到原始 src, 看到的是 SNAT 后 src)
    - firewall_groups: 按 firewall_id 分组, key = firewall.id,
        value = {'firewall': Firewall, 'policies': [sp_dict, ...]}
    """

    def __init__(self, db: Session):
        self.db = db
        self.boundary_snat_map: Dict[str, Dict] = {}
        self.pending_inbound_sps: List[Dict] = []
        self.firewall_groups: Dict[int, Dict] = {}
        self.not_pushed: List[Dict] = []  # 跟 boundary 无关、无法推送的 sp
        self.warnings: List[str] = []


# ============================================================
# 链式规划器主类
# ============================================================
class ChainPlanner:
    """
    统一寻路入口: 把 firewall_matcher + nat_analyzer + splitter_v2 串起来,
    输出 ChainContext (含按 firewall 分组的 sp 列表 + pending + warnings)。
    """

    def __init__(self, db: Session):
        self.db = db
        self.splitter = PolicySplitterV2(db)
        self.nat_analyzer = NATAnalyzer(db)
        self.matcher = FirewallMatcher(db)

    # ----------------------------------------------------------
    # 主入口
    # ----------------------------------------------------------
    def generate_chain_execution_plan(
        self,
        policies: List[Policy],
        usage_time_by_id: Dict[int, str],
    ) -> ChainContext:
        """
        对一组 Policy (一个工单的全部策略) 执行链式寻路:
          - Pass 1: 拆分 → 防火墙匹配 → NAT 分析 → 分类(边界/pending/直连)
          - Pass 2: 处理 pending inbound sp (SNAT 透传)
        返回 ChainContext, 包含分组结果 + 未推送列表 + warnings。

        不做合并 (merger 留给 preview.py)。
        """
        ctx = ChainContext(self.db)

        for policy in policies:
            self._process_policy_pass1(policy, ctx, usage_time_by_id)

        self._flush_pending_sps(ctx)

        return ctx

    # ----------------------------------------------------------
    # Pass 1: 单条 policy 拆分 + 防火墙匹配 + NAT 分析 + 分类
    # ----------------------------------------------------------
    def _process_policy_pass1(
        self,
        policy: Policy,
        ctx: ChainContext,
        usage_time_by_id: Dict[int, str],
    ) -> None:
        """对单条 Policy 执行 Pass 1 处理。"""
        # 预计算一次 match_contexts (按 firewall_id 索引), 循环内复用
        try:
            match_contexts = self.matcher.match_by_policy_context(policy) or []
        except Exception as e:
            logger.warning(
                f"FirewallMatcher.match_by_policy_context 异常 policy.id={policy.id}: {e}"
            )
            match_contexts = []

        # 拆分成单 IP 策略 (笛卡尔积)
        single_ip_policies = self.splitter.split_policy_to_single_ips(
            policy.source_ip or "",
            policy.dest_ip or "",
            policy.service or "",
            policy.action or "permit",
        )

        usage_time = usage_time_by_id.get(policy.id, "")

        for sp in single_ip_policies:
            # 情况 0: sp 自带 not_pushed_reason (splitter 内部判定: same_firewall 未启用等)
            if sp["not_pushed_reason"]:
                ctx.not_pushed.append(
                    self._build_not_pushed_entry(policy, sp, sp["not_pushed_reason"], usage_time)
                )
                continue

            firewall: Firewall = sp["firewall"]
            self._ensure_firewall_group(ctx, firewall)

            match_ctx = self._find_match_ctx(match_contexts, firewall.id)
            # 注: match_ctx 基于 policy.source_ip 第一个合法 IP 算的 (FirewallMatcher._extract_first_ip),
            #     而 sp 已是单 IP 拆分产物, 两者可能不一致 (e.g. policy.src='10.1.137.137\n192.101.64.2',
            #     match_ctx 拿的是 10.1.137.137, 但 sp 可能是 192.101.64.2).
            #     D 方案严格版: sp 真实 src 才是 fw 物理上看到的 src, 所以 nat_analyzer 必须用 sp 真实 IP
            #     重新判定 zone. 这里传 match_context=None 强制走 nat_analyzer 降级路径
            #     (nat_analyzer._find_device_zone_name_by_ip 用 sp 真实 IP, 结果一定正确).
            nat_info = self.nat_analyzer.analyze_policy_with_context(
                sp["source_ip"],
                sp["dest_ip"],
                firewall,
                match_context=None,  # 强制用 sp 真实 IP 重新判定 zone
            )

            # 收集 warnings
            for warning in nat_info.get("warnings", []):
                ctx.warnings.append(
                    f"策略 {policy.id} ({sp['source_ip']} → {sp['dest_ip']}): {warning}"
                )

            # 情况 1: 边界墙 + SNAT → 登记 SNAT 转换, fw 自己用原始 src 上墙
            if (
                firewall.is_zone_boundary
                and nat_info.get("need_nat")
                and nat_info.get("nat_type") == "SNAT"
            ):
                self._handle_boundary_snat(firewall, nat_info, ctx)
                self._append_to_group(ctx, firewall, policy, sp, nat_info, usage_time)
                continue

            # 情况 2: inbound sp → 判定 src 是否需要走 Pass 2 SNAT 透传
            #
            # 关键判定 (D 方案严格版 + 直连场景兼容):
            #   - src 在某 boundary fw 管辖范围 (正向 internal 或反向 external):
            #     物理上 src 可能是 SNAT 后 IP → 暂存 pending, Pass 2 替换
            #   - src 不在任何 boundary 管辖范围: 物理上 src 就是原始直连 client IP
            #     → 直接上墙 (跟情况 3 直连 outbound 一样, 跟"防火墙只认当前进到接口的包"铁律一致)
            #
            # 错误反模式 (D 方案严格版的 bug, 2026-06-21 修):
            #   所有 inbound 都强制走 Pass 2, 找不到 boundary_match 就 unmatched,
            #   导致直连 inbound (如 client 10.1.137.137 直接访问 dst) 被错误判 unmatched.
            if sp["direction"] == "inbound":
                boundary_match = _find_boundary_fw_for_src(sp["source_ip"], firewall, self.db)
                if boundary_match:
                    ctx.pending_inbound_sps.append(
                        {
                            "policy": policy,
                            "sp": sp,
                            "firewall": firewall,
                            "match_ctx": match_ctx,
                            "boundary_match": boundary_match,
                            "original_nat_info": nat_info,
                            "usage_time": usage_time,
                        }
                    )
                else:
                    # 直连 inbound: src 不在任何 boundary 段, 物理上就是原始 IP
                    # → 直接上墙 (铁律: 防火墙只认当前进到接口的包, 直连 src 没经过 NAT)
                    self._append_to_group(ctx, firewall, policy, sp, nat_info, usage_time)
                continue

            # 情况 3: 其他 (fw outbound / fw 直连 inbound) → 直接用原始 src 上墙
            self._append_to_group(ctx, firewall, policy, sp, nat_info, usage_time)

    # ----------------------------------------------------------
    # 情况 1: 边界墙 + SNAT 转换登记
    # ----------------------------------------------------------
    def _handle_boundary_snat(
        self,
        firewall: Firewall,
        nat_info: Dict,
        ctx: ChainContext,
    ) -> None:
        """
        边界墙触发 SNAT 时, 登记到 boundary_snat_map[target_region],
        供 Pass 2 时下游 fw 查 SNAT 后 src。

        target_region 推导 (跟 D 方案严格版一致):
          - 入向 (source_zone=external): 转换后 src 进入 fw internal 一侧,
            下游 fw (同 covered_region) 看到 src = 转换后 IP
            → target_region = firewall.covered_region
          - 出向 (source_zone=internal): 转换后 src 落在 fw external 一侧,
            下游 fw (对方 covered_region) 看到 src = 转换后 IP
            → target_region = cfg.dest_zone (对方 covered_region)
        """
        translated_src_ip = nat_info["snat_address"]

        if nat_info.get("source_zone") == "external":
            # 入向 SNAT
            target_region = firewall.covered_region or firewall.region
        else:
            # 出向 SNAT
            cfg = self._lookup_zone_access_cfg(firewall)
            # 找不到 cfg 时不能再 fallback 到 firewall.covered_region (那是同侧, 不是对方)
            # → 这种情况 SNAT 转换对下游 fw 无意义, 但仍登记, 由 preview 端排查告警
            target_region = cfg.dest_zone if cfg else (firewall.covered_region or firewall.region)

        ctx.boundary_snat_map[target_region] = {
            "translated_src_ip": translated_src_ip,
            "via_firewall": {"id": firewall.id, "name": firewall.name},
            "firewall_id": firewall.id,
        }

    def _lookup_zone_access_cfg(self, firewall: Firewall) -> Optional[ZoneAccessConfig]:
        """
        找本墙的出向 cfg (source_zone=本墙, dest_zone=对方)。

        优先级:
          1. cfg.dest_zone == firewall.external_zone_name (理想匹配)
          2. cfg.source_zone == firewall.covered_region (兼容命名不一致)
          3. substring 双向匹配 (兜底)
        """
        cfg = (
            self.db.query(ZoneAccessConfig)
            .filter_by(firewall_id=firewall.id, dest_zone=firewall.external_zone_name)
            .first()
        )
        if cfg:
            return cfg

        # Fallback 1: zone_name 命名不一致 (e.g. fw.external_zone_name="untrust" vs cfg.dest_zone="生产区")
        all_cfgs = (
            self.db.query(ZoneAccessConfig).filter_by(firewall_id=firewall.id).all()
        )
        own_region = firewall.covered_region or firewall.region
        for c in all_cfgs:
            if c.source_zone == own_region:
                return c

        # Fallback 2: substring 匹配
        for c in all_cfgs:
            if (firewall.external_zone_name and firewall.external_zone_name in c.dest_zone) or (
                c.dest_zone and c.dest_zone in firewall.external_zone_name
            ):
                return c

        return None

    # ----------------------------------------------------------
    # Pass 2: 处理 pending inbound sp
    # ----------------------------------------------------------
    def _flush_pending_sps(self, ctx: ChainContext) -> None:
        """
        Pass 2: 用 SNAT 后 src 替换 pending inbound sp 的 src, 重新上墙。

        三层 fallback (跟 D 方案严格版一致):
          1. boundary_snat_map 命中 + 非自身: 用 boundary_snat_map 的 SNAT 后 src
          2. boundary_match 自带 snat_pool 兜底
          3. boundary fw 无对应方向 SNAT 池 → unmatched
        """
        for pending in ctx.pending_inbound_sps:
            policy = pending["policy"]
            sp = pending["sp"]
            firewall = pending["firewall"]
            match_ctx = pending["match_ctx"]
            boundary_match = pending["boundary_match"]
            boundary_fw = boundary_match["boundary_fw"]
            usage_time = pending["usage_time"]

            target_region_key = firewall.covered_region or firewall.region
            snat_info = ctx.boundary_snat_map.get(target_region_key)

            if snat_info and snat_info["firewall_id"] != firewall.id:
                self._append_pass2_to_group(
                    ctx, policy, sp, firewall, match_ctx,
                    snat_info["translated_src_ip"],
                    snat_info["via_firewall"],
                    usage_time,
                )
            elif boundary_match.get("snat_pool"):
                # Fallback: boundary_match 找到但 SNAT 转换没登记 (e.g. boundary fw 自己的 inbound sp
                # 应该走情况 1, 但万一漏到 pending)
                self._append_pass2_to_group(
                    ctx, policy, sp, firewall, match_ctx,
                    boundary_match["snat_pool"],
                    {"id": boundary_fw.id, "name": boundary_fw.name},
                    usage_time,
                )
            else:
                # Fallback 2: boundary fw 没配对应方向 SNAT 池, 没法做 SNAT 透传 → unmatched
                ctx.not_pushed.append(
                    self._build_not_pushed_entry(
                        policy,
                        sp,
                        f"策略 {policy.id} src={sp['source_ip']} 边界 {boundary_fw.name} "
                        f"无 {boundary_match['direction']} SNAT 池配置, 跳过",
                        usage_time,
                    )
                )

    def _append_pass2_to_group(
        self,
        ctx: ChainContext,
        policy: Policy,
        sp: Dict,
        firewall: Firewall,
        match_ctx: Optional[Dict],
        translated_src: str,
        via_firewall: Dict,
        usage_time: str,
    ) -> None:
        """
        Pass 2 上墙: 用 SNAT 后 src 替换, 重算 nat_info, 保留 SNAT 透传标识。
        """
        new_nat_info = self.nat_analyzer.analyze_policy_with_context(
            translated_src, sp["dest_ip"], firewall, match_context=match_ctx
        )
        new_nat_info = {
            **new_nat_info,
            "need_nat": False,
            "nat_type": None,
            "warnings": [w for w in new_nat_info.get("warnings", []) if "SNAT地址池" not in w],
            "snat_address": translated_src,
            "via_firewall": via_firewall,
        }
        self._append_to_group(
            ctx, firewall, policy, sp, new_nat_info, usage_time,
            source_ip_override=translated_src,
        )

    # ----------------------------------------------------------
    # 上墙 / 未推送 / 分组 辅助
    # ----------------------------------------------------------
    def _ensure_firewall_group(self, ctx: ChainContext, firewall: Firewall) -> None:
        if firewall.id not in ctx.firewall_groups:
            ctx.firewall_groups[firewall.id] = {"firewall": firewall, "policies": []}

    def _append_to_group(
        self,
        ctx: ChainContext,
        firewall: Firewall,
        policy: Policy,
        sp: Dict,
        nat_info: Dict,
        usage_time: str,
        source_ip_override: Optional[str] = None,
    ) -> None:
        """上墙: 把 sp 追加到 firewall_groups[fw.id]['policies']"""
        self._ensure_firewall_group(ctx, firewall)
        ctx.firewall_groups[firewall.id]["policies"].append(
            {
                "original_policy_id": policy.id,
                "source_system_name": policy.source_system_name,
                "source_ip": source_ip_override or sp["source_ip"],
                "dest_system_name": policy.dest_system_name,
                "dest_ip": sp["dest_ip"],
                "service": sp["service"],
                "action": sp["action"],
                "direction": sp["direction"],
                "nat_info": nat_info,
                "使用时间": usage_time,
                "original_data": {
                    "source_system_name": policy.source_system_name,
                    "dest_system_name": policy.dest_system_name,
                },
            }
        )

    def _build_not_pushed_entry(
        self,
        policy: Policy,
        sp: Dict,
        reason: str,
        usage_time: str,
    ) -> Dict:
        return {
            "original_policy_id": policy.id,
            "source_system_name": policy.source_system_name,
            "source_ip": sp["source_ip"],
            "dest_system_name": policy.dest_system_name,
            "dest_ip": sp["dest_ip"],
            "service": sp["service"],
            "action": sp["action"],
            "not_pushed_reason": reason,
            "使用时间": usage_time,
        }

    @staticmethod
    def _find_match_ctx(match_contexts: List[Dict], firewall_id: int) -> Optional[Dict]:
        return next(
            (m for m in match_contexts if m.get("firewall_id") == firewall_id),
            None,
        )


# ============================================================
# D 方案 helper: 找 src_ip 关联的 boundary fw + SNAT 池
# ============================================================
def _find_boundary_fw_for_src(
    src_ip: str, current_fw: Firewall, db: Session
) -> Optional[Dict]:
    """
    找 src_ip 关联的 boundary fw + SNAT 池 (用于 D 方案 Pass 2 透传).

    D 方案严格版: 支持正反向 SNAT 透传.
      正向访问: src 在 boundary fw internal 段 (src 在 boundary 后面, boundary outbound SNAT)
      反向访问: src 在 boundary fw external 段 (src 在 boundary 前面, boundary inbound SNAT)
      这两种情况下, 当前 fw 物理上看到的 src 应该是 SNAT 后 IP (Pass 2 替换)

    Returns:
      None — 没命中 (sp.src 不在任何 boundary fw 管辖范围)
      {"boundary_fw": Firewall, "snat_pool": str, "direction": "outbound"|"inbound"}
    """
    if not src_ip or src_ip.strip().lower() in ("any", "0.0.0.0"):
        return None
    try:
        src_ip_obj = ipaddress.ip_address(src_ip)
    except ValueError:
        return None

    other_boundary_fws = (
        db.query(Firewall)
        .filter(
            Firewall.id != current_fw.id,
            Firewall.is_zone_boundary == 1,
        )
        .all()
    )

    for other_fw in other_boundary_fws:
        # 正向: src 在 boundary fw internal 段 (boundary outbound SNAT)
        cidr_text = other_fw.internal_protected_ips or ""
        for line in cidr_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                if src_ip_obj in ipaddress.ip_network(line, strict=False):
                    return {
                        "boundary_fw": other_fw,
                        "snat_pool": other_fw.outbound_snat_pool,
                        "direction": "outbound",
                    }
            except Exception:
                continue

        # 反向: src 在 boundary fw external 段 (boundary inbound SNAT)
        cidr_text = other_fw.external_protected_ips or ""
        for line in cidr_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                if src_ip_obj in ipaddress.ip_network(line, strict=False):
                    return {
                        "boundary_fw": other_fw,
                        "snat_pool": other_fw.inbound_snat_pool,
                        "direction": "inbound",
                    }
            except Exception:
                continue

    return None
