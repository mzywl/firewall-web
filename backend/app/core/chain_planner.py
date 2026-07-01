"""
链式寻路 + NAT 透传规划器 (chain_planner) — 精准收敛修复版

核心修复：
  1. 解决非关联核心墙由于 Fallback Zone 乱入问题：必须真实命中【明细资产】。
  2. 修复阶段一：确保透明边界墙不会因为提前 break 被跳过，通过 visited 机制支持 NAT 级联寻路。
  3. 修复阶段二/三：核心墙严格遵循“先 NAT 后原始”互斥下发，杜绝同一台墙双发。
"""
from typing import Dict, List, Optional, Tuple
import logging

from sqlalchemy.orm import Session
from app.models import Firewall, Policy
from app.core.firewall_matcher import FirewallMatcher
from app.core.nat_analyzer import NATAnalyzer
from app.core.policy_splitter_v2 import PolicySplitterV2

logger = logging.getLogger(__name__)


class ChainContext:
    def __init__(self, db: Session):
        self.db = db
        self.firewall_groups: Dict[int, Dict] = {}
        self.not_pushed: List[Dict] = []
        self.warnings: List[str] = []


class ChainPlanner:
    def __init__(self, db: Session):
        self.db = db
        self.splitter = PolicySplitterV2(db)
        self.nat_analyzer = NATAnalyzer(db)
        self.matcher = FirewallMatcher(db)

    def generate_chain_execution_plan(
        self,
        policies: List[Policy],
        usage_time_by_id: Dict[int, str],
    ) -> ChainContext:
        ctx = ChainContext(self.db)

        all_fws = self.db.query(Firewall).filter(Firewall.is_active == 1).all()
        boundary_fws = [f for f in all_fws if f.is_zone_boundary == 1]
        internal_fws = [f for f in all_fws if f.is_zone_boundary != 1]

        for policy in policies:
            usage_time = usage_time_by_id.get(policy.id, "")
            single_ip_policies = self.splitter.split_policy_to_single_ips(
                policy.source_ip or "", policy.dest_ip or "", policy.service or "", "permit"
            )

            for sp in single_ip_policies:
                if sp.get("warning_reason"):
                    ctx.warnings.append(f"策略 {policy.id} ({sp['source_ip']} → {sp['dest_ip']}): {sp['warning_reason']}")
                    continue
                if sp.get("not_pushed_reason"):
                    ctx.not_pushed.append(self._build_not_pushed_entry(policy, sp, sp["not_pushed_reason"], usage_time))
                    continue

                self._execute_three_stage_pipeline(policy, sp, boundary_fws, internal_fws, ctx, usage_time)

        return ctx

    def _execute_three_stage_pipeline(
        self,
        policy: Policy,
        sp: Dict,
        boundary_fws: List[Firewall],
        internal_fws: List[Firewall],
        ctx: ChainContext,
        usage_time: str
    ) -> None:
        original_src = sp["source_ip"]
        target_dst = sp["dest_ip"]

        # ============================================================
        # 【阶段一】: 边界墙迭代清洗与推导
        # ============================================================
        current_src = original_src
        nat_timeline: List[Tuple[Firewall, str]] = []
        visited_b_fws = set()

        # 最多支持 5 层级联 NAT 转换寻路
        for _ in range(5):
            changed_in_this_round = False

            for b_fw in boundary_fws:
                # 已经成功寻路处理过的边界墙不再重复撞击
                if b_fw.id in visited_b_fws:
                    continue

                asset_match = self.matcher.match_by_ip_assets(current_src, target_dst, b_fw)
                if asset_match["source_zone_name"] is None:
                    continue

                # 真实命中安全域资产，标记为已访问
                visited_b_fws.add(b_fw.id)
                nat_info = self.nat_analyzer.analyze_policy_with_context(current_src, target_dst, b_fw)

                if nat_info.get("need_nat") and nat_info.get("nat_type") == "SNAT" and nat_info.get("snat_address"):
                    # 发生 SNAT，记录转换并准备下发
                    current_src = nat_info["snat_address"]
                    nat_timeline.append((b_fw, current_src))
                    changed_in_this_round = True

                    prev_src = nat_timeline[-2][1] if len(nat_timeline) > 1 else original_src
                    self._append_to_group(ctx, b_fw, policy, sp, nat_info, usage_time, source_ip_override=prev_src)

                    # 核心修复：一旦 IP 发生转换，立刻中断当前内循环，用新 IP 重新撞击剩下的边界墙
                    break
                else:
                    # 边界墙没触发 SNAT（如透明模式/路由墙），正常下发直连策略
                    if asset_match["source_zone_name"] or asset_match["dest_zone_name"]:
                        self._append_to_group(ctx, b_fw, policy, sp, nat_info, usage_time, source_ip_override=current_src)

            # 如果这一轮遍历了所有剩下的墙且没有发生 NAT，寻路结束
            if not changed_in_this_round:
                break

        final_stable_src = current_src

        # ============================================================
        # 【阶段二 & 阶段三并网精准分流】: 核心核心墙入场
        # ============================================================
        for i_fw in internal_fws:
            fw_handled = False

            # 核心修复：优先判断是否作为【下游核心墙】命中 NAT 转换后的地址
            if nat_timeline:
                asset_with_nat = self.matcher.match_by_ip_assets(final_stable_src, target_dst, i_fw)
                if asset_with_nat["source_zone_name"] is not None:
                    last_boundary_fw, _ = nat_timeline[-1]
                    nat_info_nat = self.nat_analyzer.analyze_policy_with_context(final_stable_src, target_dst, i_fw)

                    pass_through_nat_info = {
                        "need_nat": False,
                        "nat_type": None,
                        "warnings": [w for w in nat_info_nat.get("warnings", []) if "SNAT地址池" not in w],
                        "snat_address": final_stable_src,
                        "via_firewall": {"id": last_boundary_fw.id, "name": last_boundary_fw.name},
                        "source_zone_name": asset_with_nat["source_zone_name"] or nat_info_nat.get("source_zone_name"),
                        "dest_zone_name": asset_with_nat["dest_zone_name"] or nat_info_nat.get("dest_zone_name"),
                    }

                    self._append_to_group(
                        ctx=ctx, firewall=i_fw, policy=policy, sp=sp, nat_info=pass_through_nat_info,
                        usage_time=usage_time,
                        source_ip_override=final_stable_src,
                        original_source_ip=original_src
                    )
                    fw_handled = True  # 标记为已处理，防止双发

            # 如果不是下游墙（或未发生 NAT），作为【上游核心墙】撞击原始 IP
            if not fw_handled:
                asset_with_origin = self.matcher.match_by_ip_assets(original_src, target_dst, i_fw)
                if asset_with_origin["source_zone_name"] is not None:
                    nat_info = self.nat_analyzer.analyze_policy_with_context(original_src, target_dst, i_fw)
                    self._append_to_group(
                        ctx=ctx, firewall=i_fw, policy=policy, sp=sp, nat_info=nat_info,
                        usage_time=usage_time, source_ip_override=original_src
                    )

    def _ensure_firewall_group(self, ctx: ChainContext, firewall: Firewall) -> None:
        if firewall.id not in ctx.firewall_groups:
            ctx.firewall_groups[firewall.id] = {"firewall": firewall, "policies": []}

    def _append_to_group(
        self, ctx: ChainContext, firewall: Firewall, policy: Policy, sp: Dict,
        nat_info: Dict, usage_time: str, source_ip_override: Optional[str] = None,
        original_source_ip: Optional[str] = None,
    ) -> None:
        self._ensure_firewall_group(ctx, firewall)

        for warning in nat_info.get("warnings", []):
            ctx.warnings.append(f"策略 {policy.id} ({sp['source_ip']} → {sp['dest_ip']}): {warning}")

        entry = {
            "original_policy_id": policy.id,
            "source_system_name": policy.source_system_name,
            "source_ip": source_ip_override or sp["source_ip"],
            "dest_system_name": policy.dest_system_name,
            "dest_ip": sp["dest_ip"],
            "service": sp["service"],
            "action": sp.get("action", "permit"),
            "direction": sp.get("direction", "outbound"),
            "src_zone_name": nat_info.get("source_zone_name"),
            "dst_zone_name": nat_info.get("dest_zone_name"),
            "nat_info": nat_info,
            "使用时间": usage_time,
        }

        if original_source_ip is not None:
            entry["original_source_ip"] = original_source_ip

        entry["original_data"] = {
            "source_system_name": policy.source_system_name,
            "dest_system_name": policy.dest_system_name,
        }

        policies_list = ctx.firewall_groups[firewall.id]["policies"]
        # 精准防重：如果当前墙里已经有了相同源 IP、目的 IP、服务的策略，不再重复塞
        if not any(p["source_ip"] == entry["source_ip"] and p["dest_ip"] == entry["dest_ip"] and p["service"] == entry["service"] for p in policies_list):
            policies_list.append(entry)

    def _build_not_pushed_entry(self, policy: Policy, sp: Dict, reason: str, usage_time: str) -> Dict:
        return {
            "original_policy_id": policy.id,
            "source_system_name": policy.source_system_name,
            "source_ip": sp["source_ip"],
            "dest_system_name": policy.dest_system_name,
            "dest_ip": sp["dest_ip"],
            "service": sp["service"],
            "action": sp.get("action", "permit"),
            "not_pushed_reason": reason,
            "使用时间": usage_time,
        }