"""
IP 地址格式化工具
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
        支持多种分隔符：顿号、逗号、换行符、空格
        
        Args:
            ip_str: 原始 IP 字符串
            
        Returns:
            格式化后的 IP 字符串（换行符分隔）
        """
        if not ip_str:
            return ""
        
        try:
            # 1. 分割 IP（支持多种分隔符）
            ip_str = str(ip_str).strip()
            # 统一替换为换行符
            ip_str = ip_str.replace('、', '\n').replace(',', '\n').replace(' ', '\n')
            ips = [ip.strip() for ip in ip_str.split('\n') if ip.strip()]
            
            if not ips:
                return ""
            
            # 2. 清理每个 IP
            cleaned_ips = []
            for ip in ips:
                cleaned = IPFormatter._clean_ip(ip)
                if cleaned:
                    cleaned_ips.append(cleaned)
            
            # 3. 添加掩码
            ips_with_mask = IPFormatter._add_mask(cleaned_ips)
            
            # 4. 合并连续 IP（可选）
            # merged_ips = IPFormatter._merge_continuous_ips(ips_with_mask)
            
            # 5. 返回格式化后的字符串
            return '\n'.join(ips_with_mask)
            
        except Exception as e:
            logger.warning(f"IP 格式化失败: {ip_str}, 错误: {str(e)}")
            return ip_str
    
    @staticmethod
    def _clean_ip(ip: str) -> str:
        """清理单个 IP 地址"""
        ip = ip.strip()
        
        # 去除特殊字符（保留 IP 相关字符）
        ip = re.sub(r'[^\d.\-/]', '', ip)
        
        return ip
    
    @staticmethod
    def _add_mask(ips: List[str]) -> List[str]:
        """
        为 IP 地址添加掩码
        - 10.0.0.0 → 10.0.0.0/8
        - 10.1.0.0 → 10.1.0.0/16
        - 10.1.1.0 → 10.1.1.0/24
        - 10.1.1.1 → 10.1.1.1（单个IP不加掩码）
        """
        result = []
        
        for ip in ips:
            # 如果已经有掩码或是 IP 段，直接保留
            if '/' in ip or '-' in ip:
                result.append(ip)
                continue
            
            # 匹配标准 IP 格式
            if re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', ip):
                parts = ip.split('.')
                
                # 根据末尾的 0 判断掩码
                if parts[1] == '0' and parts[2] == '0' and parts[3] == '0':
                    result.append(f"{ip}/8")
                elif parts[2] == '0' and parts[3] == '0':
                    result.append(f"{ip}/16")
                elif parts[3] == '0':
                    result.append(f"{ip}/24")
                else:
                    # 单个 IP，不加掩码
                    result.append(ip)
            else:
                result.append(ip)
        
        return result
    
    @staticmethod
    def _merge_continuous_ips(ips: List[str]) -> List[str]:
        """
        合并连续的 IP 地址为范围
        例如：[10.1.1.1, 10.1.1.2, 10.1.1.3] → [10.1.1.1-10.1.1.3]
        """
        # 过滤出纯 IP（不包含掩码和范围）
        pure_ips = []
        other_ips = []
        
        for ip in ips:
            if '/' in ip or '-' in ip:
                other_ips.append(ip)
            elif re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', ip):
                pure_ips.append(ip)
            else:
                other_ips.append(ip)
        
        if not pure_ips:
            return other_ips
        
        # 排序
        try:
            pure_ips = sorted(pure_ips, key=socket.inet_aton)
        except Exception:
            return ips
        
        # 合并连续 IP
        merged = []
        continuous = []
        
        for i in range(len(pure_ips)):
            if i == len(pure_ips) - 1:
                # 最后一个 IP
                if len(continuous) > 1:
                    merged.append(f"{continuous[0]}-{continuous[-1]}")
                else:
                    merged.append(pure_ips[-1])
                break
            
            current = pure_ips[i].split('.')
            next_ip = pure_ips[i + 1].split('.')
            
            # 检查是否连续（只有最后一位不同，且差值为 1）
            if (current[0] == next_ip[0] and 
                current[1] == next_ip[1] and 
                current[2] == next_ip[2] and 
                int(next_ip[3]) - int(current[3]) == 1):
                
                continuous.append(pure_ips[i])
                continuous.append(pure_ips[i + 1])
                continuous = list(set(continuous))
                continuous = sorted(continuous, key=socket.inet_aton)
            else:
                if len(continuous) > 1:
                    merged.append(f"{continuous[0]}-{continuous[-1]}")
                    continuous = []
                elif len(continuous) == 0:
                    merged.append(pure_ips[i])
                else:
                    merged.append(pure_ips[i])
                    continuous = []
        
        return merged + other_ips
    
    @staticmethod
    def extract_first_ip(ip_str: str) -> str:
        """
        提取第一个 IP 地址（用于防火墙匹配）
        处理多种分隔符和格式
        """
        if not ip_str:
            return ""
        
        ip_str = str(ip_str).strip()
        
        # 处理多种分隔符
        for sep in ['、', ',', '\n', ' ']:
            if sep in ip_str:
                ip_str = ip_str.split(sep)[0].strip()
                break
        
        # 处理 CIDR 和 IP 段
        ip_str = ip_str.split('/')[0].split('-')[0].strip()
        
        return ip_str
