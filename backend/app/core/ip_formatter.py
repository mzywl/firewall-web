"""
IP 地址格式化工具（增强版）
融合了更精细的清洗、拆分、校验、连续合并和掩码补全逻辑
"""
import re
import socket
from typing import List
import logging

logger = logging.getLogger(__name__)


class IPFormatter:
    """IP 地址格式化工具"""

    @staticmethod
    def format_ip_list(ip_str: str) -> str:
        """
        格式化 IP 地址列表
        支持多种分隔符：顿号、逗号、分号、换行符、空格
        处理流程：
        1. 文本清洗（去掉中文、特殊符号、URL 前缀、处理“止”等）
        2. 拆分为多个 token
        3. 粗筛：只保留看起来像 IP / IP 段 / CIDR 的内容
        4. 校验并过滤明显非法 IP
        5. 合并连续 IP（仅对单 IP 做连续合并）
        6. 根据末尾 0 自动补掩码（/8 /16 /24）
        7. 用换行符拼接返回
        """
        if not ip_str:
            return ""

        try:
            raw = str(ip_str).strip()
            if not raw:
                return ""

            # 1. 文本清洗
            cleaned = IPFormatter._ip_remove_special(raw)

            # 2. 拆分 token
            tokens = IPFormatter._split_to_tokens(cleaned)
            if not tokens:
                return ""

            # 3. 只保留“像 IP 的”内容（含 . / -）
            ip_like = [t for t in tokens if IPFormatter._is_ip_like(t)]
            if not ip_like:
                return ""

            # 4. 校验 & 过滤非法 IP（单 IP 做严格校验，段/CIDR/域名放过）
            ip_valid = IPFormatter._validate_ips(ip_like)

            # 5. 合并连续 IP（只对纯单 IP 做连续合并）
            ip_merged = IPFormatter._merge_continuous_ips(ip_valid)

            # 6. 自动补掩码（对纯网络地址生效）
            ip_with_mask = IPFormatter._add_mask(ip_merged)

            # 7. 返回换行分隔
            return "\n".join(ip_with_mask)

        except Exception as e:
            logger.warning(f"IP 格式化失败: {ip_str}, 错误: {str(e)}")
            # 出错时返回原始内容，避免数据丢失
            return str(ip_str)

    # ===================== 文本预处理相关 =====================

    @staticmethod
    def _ip_remove_special(text: str) -> str:
        """
        参考“IP移除特殊字符”做精简版：
        - 处理“止”表示范围
        - 去掉中文、零宽字符
        - 去掉 http/https 前缀
        - 对域名和非域名做不同处理
        """
        if not text:
            return ""

        # 处理“止”表示范围
        if "止" in text:
            text = re.sub("[\:\：]", "", text)
        text = re.sub(r"(?<=\d)?\s+止(?=\d)", "-", text)
        text = re.sub(r"(?<=\d)止(?=\d)", "-", text)

        # 去中文、零宽字符
        text = re.sub("[\u4e00-\u9fa5]", " ", text)
        text = re.sub("[\u200b]", " ", text)

        # 去掉 URL 前缀
        for prefix in ["https://", "http://", "HTTPS://", "HTTP://"]:
            text = text.replace(prefix, "")

        # 如果是域名（含 .com / .cn / .net / .tech 等），保留字母和点，交给外部域名解析
        if any(t in text for t in [".com", ".COM", ".cn", ".CN", ".net", ".NET", ".tech", ".TECH"]):
            text = re.sub(
                r"'[\s+\|\!\[\]\{\},$%^(+\"\')]+|[+()?【】;,“”！；：:，。？、@#￥%……&（）]+'",
                " ",
                text,
            )
            return text

        # 非域名：去掉所有字母，只保留数字、点、横杠、斜杠和分隔符
        text = re.sub("[A-Za-z]", "", text)
        text = re.sub(
            r"[\s+\|\!\[\]\{\}_,$%^(+\"\')]+|[+()?【】;,“”！；：:，。？、@#￥%……&（）]+",
            " ",
            text,
        )
        return text

    @staticmethod
    def _split_to_tokens(text: str) -> List[str]:
        """把一大串 IP 文本拆成一个个 token"""
        if not text:
            return []
        # 常见分隔符：空格、逗号、顿号、分号、换行等
        text = text.replace("、", " ")
        parts = re.split(r"[\s,;]+", text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _is_ip_like(s: str) -> bool:
        """粗略判断是不是 IP / IP 段 / CIDR / 域名（含点或范围符号）"""
        return "." in s or "-" in s or "/" in s

    # ===================== IP 校验与合并 =====================

    @staticmethod
    def _validate_ips(ips: List[str]) -> List[str]:
        """
        精简版 IP 校验：
        - 单 IP：用正则严格校验
        - IP 段 / CIDR / 域名：直接放过（如需更严格可再拆分校验）
        """
        valid = []
        ip_regex = (
            r"^(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\."
            r"(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\."
            r"(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\."
            r"(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])$"
        )

        for ip in ips:
            s = ip.strip()
            if not s:
                continue

            # 域名 / CIDR / IP 段：先放过
            if re.match("[A-Za-z]", s) or "/" in s or "-" in s:
                valid.append(s)
                continue

            # 单 IP 严格校验
            if re.match(ip_regex, s):
                valid.append(s)
            else:
                logger.debug(f"丢弃非法 IP: {s}")
        return valid

    @staticmethod
    def _list_return_mixed(list_str: List[str]) -> List[str]:
        """
        参考你的 list_return：
        返回带 “/” “-” 或字母的元素（IP 段、CIDR、域名等）
        """
        res = []
        for i in list_str:
            if "/" in i or "-" in i:
                res.append(i)
            elif re.match(r"[a-zA-Z]+", i):
                res.append(i)
        return res

    @staticmethod
    def _merge_continuous_ips(ips: List[str]) -> List[str]:
        """
        合并连续的 IP 地址为范围
        仅对“纯单 IP”做连续合并：
        例如：[10.1.1.1, 10.1.1.2, 10.1.1.3] → [10.1.1.1-10.1.1.3]
        其他（IP 段、CIDR、域名）保持原样
        """
        if not ips:
            return []

        # 分离出“特殊的”（段、CIDR、域名等）
        special_list = IPFormatter._list_return_mixed(ips)
        pure_ips = list(set(ips) - set(special_list))

        if not pure_ips:
            return special_list

        try:
            pure_ips = sorted(pure_ips, key=socket.inet_aton)
        except Exception as e:
            logger.debug(f"IP 排序失败，回退原列表: {e}")
            return ips

        merged = []
        buf = []

        for i in range(len(pure_ips)):
            if i == len(pure_ips) - 1:
                # 最后一个
                if len(buf) > 1:
                    merged.append(f"{buf[0]}-{buf[-1]}")
                elif len(buf) == 1:
                    merged.append(buf[0])
                else:
                    merged.append(pure_ips[-1])
                break

            cur_ip = pure_ips[i]
            next_ip = pure_ips[i + 1]

            cur_parts = cur_ip.split(".")
            next_parts = next_ip.split(".")

            # 只在最后一段连续时合并
            if (
                cur_parts[:-1] == next_parts[:-1]
                and int(next_parts[-1]) - int(cur_parts[-1]) == 1
            ):
                buf.append(cur_ip)
                buf.append(next_ip)
                buf = sorted(list(set(buf)), key=socket.inet_aton)
            else:
                if not buf:
                    merged.append(cur_ip)
                else:
                    merged.append(f"{buf[0]}-{buf[-1]}")
                    buf = []

        return merged + special_list

    # ===================== 掩码补全 =====================

    @staticmethod
    def _add_mask(ips: List[str]) -> List[str]:
        """
        为 IP 地址添加掩码（保留原有逻辑）：
        - 已经有掩码或是 IP 段，直接保留
        - 10.0.0.0 → 10.0.0.0/8
        - 10.1.0.0 → 10.1.0.0/16
        - 10.1.1.0 → 10.1.1.0/24
        - 10.1.1.1 → 10.1.1.1（单个IP不加掩码）
        """
        result = []

        for ip in ips:
            s = ip.strip()
            if not s:
                continue

            # 已有掩码或范围，直接保留
            if "/" in s or "-" in s:
                result.append(s)
                continue

            # 匹配标准 IP 格式
            m = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", s)
            if not m:
                result.append(s)
                continue

            parts = s.split(".")

            # 根据末尾的 0 判断掩码
            if parts[1] == "0" and parts[2] == "0" and parts[3] == "0":
                result.append(f"{s}/8")
            elif parts[2] == "0" and parts[3] == "0":
                result.append(f"{s}/16")
            elif parts[3] == "0":
                result.append(f"{s}/24")
            else:
                # 单个 IP，不加掩码
                result.append(s)

        return result

    # ===================== 辅助方法 =====================

    @staticmethod
    def extract_first_ip(ip_str: str) -> str:
        """
        提取第一个 IP 地址（用于防火墙匹配）
        处理多种分隔符和格式：
        - 顿号、逗号、换行、空格
        - CIDR：取斜杠前
        - IP 段：取横杠前
        """
        if not ip_str:
            return ""

        s = str(ip_str).strip()
        if not s:
            return ""

        # 先按常见分隔符截取第一个
        for sep in ["、", ",", "\n", " "]:
            if sep in s:
                s = s.split(sep)[0].strip()
                break

        # 再处理 CIDR 和 IP 段
        s = s.split("/")[0].split("-")[0].strip()

        # 做一次轻量清洗，避免带奇怪字符
        s = re.sub(r"[^\d.]", "", s)



class PortFormatter:
    """端口格式化工具（增强版）"""

    # ============================================================
    #                      对外主接口
    # ============================================================

    @staticmethod
    def format_port_list(port_str: str) -> str:
        """
        格式化端口列表：
        1. 清洗特殊字符
        2. 拆分 token
        3. 校验端口合法性
        4. 合并连续端口
        5. 返回统一格式
        """
        if not port_str:
            return ""

        try:
            raw = str(port_str).strip()
            cleaned = PortFormatter._port_remove_special(raw)
            tokens = PortFormatter._split_ports(cleaned)

            valid = PortFormatter._validate_ports(tokens)
            merged = PortFormatter._merge_continuous_ports(valid)

            return ",".join(merged)

        except Exception as e:
            logger.warning(f"端口格式化失败: {port_str}, 错误: {str(e)}")
            return str(port_str)

    # ============================================================
    #                      文本清洗
    # ============================================================

    @staticmethod
    def _port_remove_special(text: str) -> str:
        """融合你原来的 端口去除特殊字符"""
        if not text:
            return ""

        # 处理“止”表示范围
        if "止" in text:
            text = re.sub("[\:\：]", "", text)
        text = re.sub(r"(?<=\d)?\s+止(?=\d)", "-", text)
        text = re.sub(r"(?<=\d)止(?=\d)", "-", text)

        # 去中文
        text = re.sub("[\u4e00-\u9fa5]", " ", text)

        # ~ → -
        text = text.replace("~", "-")

        # 全部大写
        text = text.upper()

        # UDP: 规范化
        text = re.sub(r"UDP\：", "UDP:", text)

        # 去掉各种 TCP 标记
        text = re.sub(r"TCPP?\s*\:?", "", text)
        text = text.replace("TCP", "")

        # 特殊情况修正
        text = text.replace("80443", "80 443")

        # 去掉字母（保留 UDP:）
        if "UDP" not in text:
            text = re.sub("[A-Za-z]", "", text)

        # 去掉特殊符号
        text = re.sub(r"[^\d\-\s:]+", " ", text)

        return text

    @staticmethod
    def _split_ports(text: str) -> List[str]:
        """拆分端口 token"""
        parts = re.split(r"[\s,;]+", text)
        return [p.strip() for p in parts if p.strip()]

    # ============================================================
    #                      端口合法性校验
    # ============================================================

    @staticmethod
    def _validate_ports(ports: List[str]) -> List[str]:
        """
        校验端口合法性：
        - 支持 UDP:80、UDP:80-90
        - 支持 80、80-90
        """
        valid = []
        port_regex = r"^([0-9]|[1-9]\d{1,3}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])$"

        for p in ports:
            s = p.strip()
            if not s:
                continue

            # UDP: 前缀
            if s.startswith("UDP:"):
                body = s.replace("UDP:", "")
                if "-" in body:
                    a, b = body.split("-")
                    if re.match(port_regex, a) and re.match(port_regex, b) and int(a) < int(b):
                        valid.append(s)
                    else:
                        logger.debug(f"非法 UDP 端口段: {s}")
                else:
                    if re.match(port_regex, body):
                        valid.append(s)
                    else:
                        logger.debug(f"非法 UDP 端口: {s}")
                continue

            # 普通端口段
            if "-" in s:
                a, b = s.split("-")
                if re.match(port_regex, a) and re.match(port_regex, b) and int(a) < int(b):
                    valid.append(s)
                else:
                    logger.debug(f"非法端口段: {s}")
                continue

            # 单端口
            if re.match(port_regex, s):
                valid.append(s)
            else:
                logger.debug(f"非法端口: {s}")

        return valid

    # ============================================================
    #                      连续端口合并
    # ============================================================

    @staticmethod
    def _merge_continuous_ports(ports: List[str]) -> List[str]:
        """
        合并连续端口：
        - 80,81,82 → 80-82
        - UDP:80, UDP:81 → UDP:80-81
        """
        if not ports:
            return []

        udp_ports = []
        pure_ports = []

        for p in ports:
            if p.startswith("UDP:"):
                udp_ports.append(p)
            else:
                pure_ports.append(p)

        # 处理 UDP 端口
        udp_merged = PortFormatter._merge_udp_ports(udp_ports)

        # 处理普通端口
        pure_merged = PortFormatter._merge_normal_ports(pure_ports)

        return udp_merged + pure_merged

    @staticmethod
    def _merge_normal_ports(ports: List[str]) -> List[str]:
        """合并普通端口"""
        singles = []
        ranges = []

        for p in ports:
            if "-" in p:
                ranges.append(p)
            else:
                singles.append(int(p))

        singles = sorted(set(singles))

        merged = []
        buf = []

        for i in range(len(singles)):
            if i == len(singles) - 1:
                if len(buf) > 1:
                    merged.append(f"{buf[0]}-{buf[-1]}")
                elif len(buf) == 1:
                    merged.append(str(buf[0]))
                else:
                    merged.append(str(singles[-1]))
                break

            cur = singles[i]
            nxt = singles[i + 1]

            if nxt - cur == 1:
                buf.append(cur)
                buf.append(nxt)
                buf = sorted(set(buf))
            else:
                if not buf:
                    merged.append(str(cur))
                else:
                    merged.append(f"{buf[0]}-{buf[-1]}")
                    buf = []

        return merged + ranges

    @staticmethod
    def _merge_udp_ports(ports: List[str]) -> List[str]:
        """合并 UDP: 端口"""
        singles = []
        ranges = []

        for p in ports:
            body = p.replace("UDP:", "")
            if "-" in body:
                ranges.append(p)
            else:
                singles.append(int(body))

        singles = sorted(set(singles))

        merged = []
        buf = []

        for i in range(len(singles)):
            if i == len(singles) - 1:
                if len(buf) > 1:
                    merged.append(f"UDP:{buf[0]}-{buf[-1]}")
                elif len(buf) == 1:
                    merged.append(f"UDP:{buf[0]}")
                else:
                    merged.append(f"UDP:{singles[-1]}")
                break

            cur = singles[i]
            nxt = singles[i + 1]

            if nxt - cur == 1:
                buf.append(cur)
                buf.append(nxt)
                buf = sorted(set(buf))
            else:
                if not buf:
                    merged.append(f"UDP:{cur}")
                else:
                    merged.append(f"UDP:{buf[0]}-{buf[-1]}")
                    buf = []

        return merged + ranges
