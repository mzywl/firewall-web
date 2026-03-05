"""
Excel 文件解析模块
"""
import openpyxl
from typing import List, Dict, Any, Optional, Tuple
import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ExcelParser:
    """Excel 解析器"""
    
    # 关键字段，用于查找真正的表头
    KEY_FIELDS = ["源IP", "目的IP", "目的端口"]
    
    # 字段映射：Excel表头 -> 标准字段名
    FIELD_MAPPING = {
        # 源IP相关
        "源IP": "源IP",
        "源ip": "源IP",
        "源地址": "源IP",
        "源IP地址": "源IP",
        
        # 目的IP相关
        "目的IP": "目的IP",
        "目的ip": "目的IP",
        "目标IP": "目的IP",
        "目的地址": "目的IP",
        "目的IP地址": "目的IP",
        
        # 端口相关
        "目的端口": "目的端口",
        "目标端口": "目的端口",
        "端口": "目的端口",
        "服务端口": "目的端口",
        "服务": "目的端口",
        
        # 区域相关（映射到系统-环境-用途字段）
        "源区域": "源区域",
        "源安全域": "源区域",
        "源端系统-环境-用途": "源区域",
        "源端系统": "源区域",
        
        "目的区域": "目的区域",
        "目标区域": "目的区域",
        "目的安全域": "目的区域",
        "目的端系统-环境-用途": "目的区域",
        "目的端系统": "目的区域",
        
        # 动作相关
        "动作": "动作",
        "策略动作": "动作",
        "action": "动作",
        
        # 其他字段
        "用途": "用途",
        "策略使用目的": "策略使用目的",
        "使用时间": "使用时间",
        "备注": "备注",
    }
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.workbook = None
        self.sheet = None
        
    def parse(self) -> Dict[str, Any]:
        """
        解析 Excel 文件
        返回: {
            "headers": [...],
            "data": [...],
            "total_rows": int,
            "header_row": int
        }
        """
        try:
            self.workbook = openpyxl.load_workbook(self.file_path)
            
            # 1. 优先读取名称包含"网络策略"的 sheet
            self.sheet = self._find_network_policy_sheet()
            logger.info(f"使用 sheet: {self.sheet.title}")
            
            # 2. 查找真正的表头行
            header_row, headers = self._find_real_header()
            logger.info(f"表头行: {header_row}, 表头: {headers}")
            
            if not headers:
                raise Exception("未找到包含关键字段（源IP、目的IP、目的端口）的表头行")
            
            # 3. 读取数据（从表头行之后开始）
            data = self._read_data(headers, header_row)
            logger.info(f"读取到 {len(data)} 行数据")
            
            # 4. 标准化字段名
            data = self._normalize_field_names(data)
            
            # 5. 删除示例策略
            data = self._remove_example_policies(data)
            logger.info(f"过滤后剩余 {len(data)} 行数据")
            
            # 打印第一行数据用于调试
            if data:
                logger.info(f"第一行数据示例: {data[0]}")
            
            return {
                "headers": headers,
                "data": data,
                "total_rows": len(data),
                "header_row": header_row
            }
        except Exception as e:
            logger.error(f"Excel 解析失败: {str(e)}")
            raise Exception(f"Excel 解析失败: {str(e)}")
        finally:
            if self.workbook:
                self.workbook.close()
    
    def _find_network_policy_sheet(self) -> openpyxl.worksheet.worksheet.Worksheet:
        """
        优先读取名称包含"网络策略"的 sheet
        如果没有找到，则使用激活的 sheet
        """
        for sheet in self.workbook.worksheets:
            if "网络策略" in sheet.title:
                return sheet
        
        # 如果没有找到，返回激活的 sheet
        return self.workbook.active
    
    def _find_real_header(self) -> Tuple[int, List[str]]:
        """
        从第一行开始查找包含关键字段的行作为表头
        返回: (表头行号, 表头列表)
        """
        for row_idx in range(1, min(self.sheet.max_row + 1, 20)):  # 只查找前20行
            row = list(self.sheet[row_idx])
            row_values = [str(cell.value).strip() if cell.value else "" for cell in row]
            
            # 检查是否包含所有关键字段
            if self._contains_key_fields(row_values):
                logger.info(f"找到表头行: 第 {row_idx} 行")
                return row_idx, row_values
        
        # 如果没有找到，返回第一行作为表头
        logger.warning("未找到包含关键字段的表头行，使用第一行")
        first_row = list(self.sheet[1])
        headers = [str(cell.value).strip() if cell.value else "" for cell in first_row]
        return 1, headers
    
    def _contains_key_fields(self, row_values: List[str]) -> bool:
        """
        检查行是否包含所有关键字段
        使用更宽松的匹配策略：只要行中包含关键字段即可
        """
        # 将所有单元格值连接成一个字符串，方便查找
        row_str = " ".join([str(v).strip() for v in row_values if v])
        
        # 检查是否包含所有关键字段
        found_count = 0
        for key_field in self.KEY_FIELDS:
            if key_field in row_str:
                found_count += 1
                logger.debug(f"找到关键字段: {key_field}")
        
        result = found_count == len(self.KEY_FIELDS)
        if result:
            logger.info(f"行包含所有关键字段: {self.KEY_FIELDS}")
        
        return result
    
    def _read_data(self, headers: List[str], header_row: int) -> List[Dict[str, Any]]:
        """
        读取数据行（从表头行之后开始）
        """
        data = []
        
        for row_idx in range(header_row + 1, self.sheet.max_row + 1):
            row = list(self.sheet[row_idx])
            row_data = {}
            
            for col_idx, cell in enumerate(row):
                if col_idx < len(headers):
                    header = headers[col_idx]
                    value = cell.value
                    row_data[header] = self._format_value(value)
            
            # 跳过空行
            if any(row_data.values()):
                row_data["_row_number"] = row_idx
                data.append(row_data)
        
        return data
    
    def _normalize_field_names(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        标准化字段名
        将 Excel 中的各种字段名映射到标准字段名
        """
        normalized_data = []
        
        for row in data:
            normalized_row = {}
            
            for key, value in row.items():
                # 查找映射的标准字段名
                standard_key = self.FIELD_MAPPING.get(key, key)
                normalized_row[standard_key] = value
            
            normalized_data.append(normalized_row)
        
        return normalized_data
    
    def _remove_example_policies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        删除示例策略
        判断条件：如果同时满足以下条件，则认为是示例策略：
        - "源区域"（源端系统-环境-用途）包含 "示例"
        - "目的区域"（目的端系统-环境-用途）包含 "示例"
        """
        filtered_data = []
        
        for row in data:
            # 使用标准化后的字段名
            source_system = str(row.get("源区域", ""))
            dest_system = str(row.get("目的区域", ""))
            
            # 如果两个字段都包含"示例"，则跳过
            if "示例" in source_system and "示例" in dest_system:
                logger.info(f"过滤示例策略: 源={source_system}, 目的={dest_system}")
                continue
            
            filtered_data.append(row)
        
        return filtered_data
    
    def _format_value(self, value: Any) -> Any:
        """格式化单元格值"""
        if value is None:
            return ""
        
        # 日期类型
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        
        # 字符串类型，去除首尾空格
        if isinstance(value, str):
            return value.strip()
        
        return value
    
    @staticmethod
    def normalize_ip(ip_str: str) -> str:
        """标准化 IP 地址"""
        if not ip_str:
            return ""
        
        # 去除空格
        ip_str = ip_str.strip()
        
        # 处理 IP 段（例如：192.168.1.1-192.168.1.10）
        if "-" in ip_str and not ip_str.startswith("-"):
            return ip_str
        
        # 处理 CIDR（例如：192.168.1.0/24）
        if "/" in ip_str:
            return ip_str
        
        # 单个 IP
        return ip_str
    
    @staticmethod
    def normalize_port(port_str: str) -> str:
        """标准化端口"""
        if not port_str:
            return ""
        
        port_str = str(port_str).strip()
        
        # 处理端口范围（例如：8080-8090）
        if "-" in port_str:
            return port_str
        
        # 处理多个端口（例如：80,443,8080）
        if "," in port_str:
            return port_str
        
        return port_str
