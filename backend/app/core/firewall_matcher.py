"""
防火墙智能匹配器 (纯 IP 资产维增强版) — 三阶段流水线对齐版

说明:
  - 符合业务特殊定制逻辑：南北向单侧落点不上墙；同域不上墙。为三阶段寻路提供硬判定。
"""
from typing import Optional, Tuple, Dict, Any
import ipaddress
import logging
from sqlalchemy.orm import Session

from app.models import Firewall, FirewallZone

logger = logging.getLogger(__name__)


class FirewallMatcher:
    def __init__(self, db: Session):
        self.db = db

    def find_zone_by_single_ip(
            self, ip_str: str, firewall: Firewall, field_label: str = "IP"
    ) -> Tuple[Optional[str], Optional[FirewallZone]]:
        ip_obj = self._parse_to_ip_object(ip_str, field_label)
        if not ip_obj:
            return None, None
        return self._find_zone_by_ip(ip_obj, firewall)

    def match_by_ip_assets(self, source_ip: str, dest_ip: str, firewall: Firewall) -> Dict[str, Any]:
        src_ip_obj = self._parse_to_ip_object(source_ip, "源IP")
        dst_ip_obj = self._parse_to_ip_object(dest_ip, "目的IP")

        fw_src_zone, src_zone_obj = self._find_zone_by_ip(src_ip_obj, firewall)
        fw_dst_zone, dst_zone_obj = self._find_zone_by_ip(dst_ip_obj, firewall)

        # 业务定制逻辑：南北向单侧不落资产、同域不出策略，在此直接硬阻断
        if fw_dst_zone is None:
            fw_src_zone = None
        if fw_src_zone == fw_dst_zone :
            fw_src_zone = None

        return {
            "source_zone_name": fw_src_zone,
            "source_zone_obj": src_zone_obj,
            "dest_zone_name": fw_dst_zone,
            "dest_zone_obj": dst_zone_obj,
        }

    def _find_zone_by_ip(
            self, ip_obj: Optional[ipaddress.IPv4Address], fw: Firewall
    ) -> Tuple[Optional[str], Optional[FirewallZone]]:
        if not ip_obj or not fw.zones:
            return None, None

        for zone in fw.zones:
            if zone.protected_ips:
                for ip_range in zone.protected_ips.strip().split('\n'):
                    ip_range = ip_range.strip()
                    if not ip_range:
                        continue
                    try:
                        if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                            return zone.zone_name, zone
                    except Exception:
                        continue
        return None, None

    def _parse_to_ip_object(self, ip_str: str, field_label: str) -> Optional[ipaddress.IPv4Address]:
        if not ip_str:
            return None
        extracted = self._extract_first_ip(ip_str)
        if not extracted:
            return None
        try:
            if '/' in extracted:
                return ipaddress.ip_network(extracted, strict=False).network_address
            return ipaddress.ip_address(extracted)
        except Exception as e:
            logger.warning(f"[{field_label}] 无法转换文本 '{ip_str}' 为有效IP对象: {e}")
            return None

    def _extract_first_ip(self, ip_str: str) -> str:
        if not ip_str:
            return ""
        normalized = ip_str.replace('\r\n', '\n').replace(',', '\n').replace(';', '\n').replace('；', '\n')
        for line in normalized.split('\n'):
            line = line.strip()
            if not line:
                continue
            for part in line.split(','):
                part = part.strip()
                if not part:
                    continue
                if '-' in part and '/' not in part:
                    first = part.split('-')[0].strip()
                    try:
                        ipaddress.ip_address(first)
                        return first
                    except ValueError:
                        continue
                if '/' in part:
                    first = part.split('/')[0].strip()
                    try:
                        ipaddress.ip_address(first)
                        return first
                    except ValueError:
                        continue
                try:
                    ipaddress.ip_address(part)
                    return part
                except ValueError:
                    continue
        return ""