"""
Excel 文件解析模块
"""
import openpyxl
from typing import List, Dict, Any, Optional, Tuple
import re
from datetime import datetime


class ExcelParser:
    """Excel 解析器"""
    
    # 关键字段，用于查找真正的表头
    KEY_FIELDS = ["源IP", "目的IP", "目的端口"]
    
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
            
            # 2. 查找真正的表头行
            header_row, headers = self._find_real_header()
            
            if not headers:
                raise Exception("未找到包含关键字段（源IP、目的IP、目的端口）的表头行")
            
            # 3. 读取数据（从表头行之后开始）
            data = self._read_data(headers, header_row)
            
            # 4. 删除示例策略
            data = self._remove_example_policies(data)
            
            return {
                "headers": headers,
                "data": data,
                "total_rows": len(data),
                "header_row": header_row
            }
        except Exception as e:
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
        for row_idx in range(1, self.sheet.max_row + 1):
            row = list(self.sheet[row_idx])
            row_values = [str(cell.value).strip() if cell.value else "" for cell in row]
            
            # 检查是否包含所有关键字段
            if self._contains_key_fields(row_values):
                return row_idx, row_values
        
        # 如果没有找到，返回第一行作为表头
        first_row = list(self.sheet[1])
        headers = [str(cell.value).strip() if cell.value else "" for cell in first_row]
        return 1, headers
    
    def _contains_key_fields(self, row_values: List[str]) -> bool:
        """
        检查行是否包含所有关键字段
        """
        found_fields = set()
        
        for value in row_values:
            for key_field in self.KEY_FIELDS:
                if key_field in value:
                    found_fields.add(key_field)
        
        # 必须包含所有关键字段
        return len(found_fields) == len(self.KEY_FIELDS)
    
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
    
    def _remove_example_policies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        删除示例策略
        判断条件：如果同时满足以下条件，则认为是示例策略：
        - "源端系统-环境-用途" 包含 "示例"
        - "目的端系统-环境-用途" 包含 "示例"
        """
        filtered_data = []
        
        for row in data:
            source_system = str(row.get("源端系统-环境-用途", ""))
            dest_system = str(row.get("目的端系统-环境-用途", ""))
            
            # 如果两个字段都包含"示例"，则跳过
            if "示例" in source_system and "示例" in dest_system:
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
