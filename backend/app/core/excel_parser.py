"""
Excel 文件解析模块
"""
import openpyxl
from typing import List, Dict, Any
import re
from datetime import datetime


class ExcelParser:
    """Excel 解析器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.workbook = None
        self.sheet = None
        
    def parse(self) -> Dict[str, Any]:
        """
        解析 Excel 文件
        返回: {
            "headers": [...],
            "data": [...]
        }
        """
        try:
            self.workbook = openpyxl.load_workbook(self.file_path)
            self.sheet = self.workbook.active
            
            # 读取表头
            headers = self._read_headers()
            
            # 读取数据
            data = self._read_data(headers)
            
            return {
                "headers": headers,
                "data": data,
                "total_rows": len(data)
            }
        except Exception as e:
            raise Exception(f"Excel 解析失败: {str(e)}")
        finally:
            if self.workbook:
                self.workbook.close()
    
    def _read_headers(self) -> List[str]:
        """读取表头（第一行）"""
        headers = []
        for cell in self.sheet[1]:
            headers.append(str(cell.value) if cell.value else "")
        return headers
    
    def _read_data(self, headers: List[str]) -> List[Dict[str, Any]]:
        """读取数据行"""
        data = []
        for row_idx, row in enumerate(self.sheet.iter_rows(min_row=2, values_only=True), start=2):
            row_data = {}
            for col_idx, value in enumerate(row):
                if col_idx < len(headers):
                    header = headers[col_idx]
                    row_data[header] = self._format_value(value)
            
            # 跳过空行
            if any(row_data.values()):
                row_data["_row_number"] = row_idx
                data.append(row_data)
        
        return data
    
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
