"""
Excel 文件解析模块
"""
import openpyxl
from typing import List, Dict, Any, Optional, Tuple
import re
from datetime import datetime
import logging
from app.core.ip_formatter import IPFormatter,PortFormatter

logger = logging.getLogger(__name__)


class ExcelParser:
    """Excel 解析器"""

    # 关键字段，用于查找真正的表头
    KEY_FIELDS = ["源IP", "目的IP", "目的端口"]

    # 字段映射：Excel表头 -> 标准英文字段名
    FIELD_MAPPING = {
        # 源IP相关
        "源IP": "source_ip",
        "源ip": "source_ip",
        "源地址": "source_ip",
        "源IP地址": "source_ip",

        # 目的IP相关
        "目的IP": "dest_ip",
        "目的ip": "dest_ip",
        "目标IP": "dest_ip",
        "目的地址": "dest_ip",
        "目的IP地址": "dest_ip",

        # 端口相关
        "目的端口": "service",
        "目标端口": "service",
        "端口": "service",
        "服务端口": "service",
        "服务": "service",

        # 区域相关（映射到系统-环境-用途字段）
        "源区域": "source_zone",
        "源安全域": "source_zone",
        "源端系统-环境-用途": "source_zone",
        "源端系统": "source_zone",

        "目的区域": "dest_zone",
        "目标区域": "dest_zone",
        "目的安全域": "dest_zone",
        "目的端系统-环境-用途": "dest_zone",
        "目的端系统": "dest_zone",

        # 动作相关
        "动作": "action",
        "策略动作": "action",
        "action": "action",

        # 其他字段
        "用途": "purpose",
        "策略使用目的": "policy_purpose",
        "使用时间": "usage_time",
        "备注": "remark",
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
            
            # 移除空列
            data, headers = self._remove_empty_columns(data, headers)
            
            # 保存原始数据（保留中文列头）
            original_data = [dict(row) for row in data]

            # 4. 第一次格式化：格式化 IP 地址（保留中文列头）
            formatted_v1_data = self._format_ip_addresses([dict(row) for row in data])
            logger.info(f"第一次格式化完成，共 {len(formatted_v1_data)} 行数据")

            # 5. 第二次格式化：删除示例策略（保留中文列头）
            formatted_v2_data = self._remove_example_policies([dict(row) for row in formatted_v1_data])
            logger.info(f"第二次格式化完成（删除示例策略），剩余 {len(formatted_v2_data)} 行数据")

            # 6. 转换成英文字段名（用于保存到 Policy 表）
            normalized_data = self._normalize_field_names([dict(row) for row in formatted_v2_data])
            logger.info(f"字段名标准化完成")

            # 打印第一行数据用于调试
            if normalized_data:
                logger.info(f"第一行数据示例: {normalized_data[0]}")

            return {
                "headers": headers,
                "data": normalized_data,  # 用于保存到 Policy 表（英文字段名）
                "original_data": original_data,  # 版本1：原始数据（中文列头）
                "formatted_v1_data": formatted_v1_data,  # 版本2：第一次格式化（中文列头）
                "formatted_v2_data": formatted_v2_data,  # 版本3：第二次格式化（中文列头）
                "total_rows": len(normalized_data),
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

    def _remove_empty_columns(
            self,
            data: List[Dict[str, Any]],
            headers: List[str],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        移除数据中的空列，并同步更新 headers
        空列定义：在所有数据行中，该列的值都为空 / None / 纯空白
        """
        if not data or not headers:
            return data, headers

        empty_columns = []

        # 只以 headers 中的列为准，避免误删内部字段（比如 _row_number）
        for col in headers:
            is_empty = True
            for row in data:
                value = row.get(col, "")
                if value not in ("", None) and str(value).strip() != "":
                    is_empty = False
                    break
            if is_empty:
                empty_columns.append(col)

        # 从每一行中删除这些空列
        if empty_columns:
            for row in data:
                for col in empty_columns:
                    row.pop(col, None)

        # 同步更新 headers
        new_headers = [h for h in headers if h not in empty_columns]

        return data, new_headers

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
        要求：每个关键字段必须是独立的列值（短文本），避免匹配到说明文字
        """
        found_fields = set()

        for value in row_values:
            value = str(value).strip()

            # 只检查短文本（长度 < 50 字符），避免匹配到说明文字
            if len(value) < 50:
                for key_field in self.KEY_FIELDS:
                    if key_field in value:
                        found_fields.add(key_field)
                        logger.debug(f"找到关键字段: {key_field} (在 '{value}' 中)")

        result = len(found_fields) == len(self.KEY_FIELDS)
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

    def _format_ip_addresses(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        使用更精细的 IP / 端口格式化逻辑
        支持中文列头和英文字段名
        """
        for row in data:
            # 查找源IP字段（支持中文和英文）
            source_ip_key = None
            for key in row.keys():
                if key in ['source_ip', '源IP', '源ip', '源地址', '源IP地址']:
                    source_ip_key = key
                    break
            
            if source_ip_key and row[source_ip_key]:
                row[source_ip_key] = IPFormatter.format_ip_list(row[source_ip_key])

            # 查找目的IP字段
            dest_ip_key = None
            for key in row.keys():
                if key in ['dest_ip', '目的IP', '目的ip', '目标IP', '目的地址', '目的IP地址']:
                    dest_ip_key = key
                    break
            
            if dest_ip_key and row[dest_ip_key]:
                row[dest_ip_key] = IPFormatter.format_ip_list(row[dest_ip_key])

            # 查找服务/端口字段
            service_key = None
            for key in row.keys():
                if key in ['service', '目的端口', '目标端口', '端口', '服务端口', '服务']:
                    service_key = key
                    break
            
            if service_key and row[service_key]:
                row[service_key] = PortFormatter.format_port_list(row[service_key])

        return data

    def _remove_example_policies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        删除示例策略
        判断条件：如果同时满足以下条件，则认为是示例策略：
        - 源区域字段包含 "示例"
        - 目的区域字段包含 "示例"
        支持中文列头和英文字段名
        """
        filtered_data = []

        for row in data:
            # 查找源区域字段
            source_zone_key = None
            for key in row.keys():
                if key in ['source_zone', '源区域', '源安全域', '源端系统-环境-用途', '源端系统']:
                    source_zone_key = key
                    break
            
            # 查找目的区域字段
            dest_zone_key = None
            for key in row.keys():
                if key in ['dest_zone', '目的区域', '目标区域', '目的安全域', '目的端系统-环境-用途', '目的端系统']:
                    dest_zone_key = key
                    break
            
            source_system = str(row.get(source_zone_key, "")) if source_zone_key else ""
            dest_system = str(row.get(dest_zone_key, "")) if dest_zone_key else ""

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

if __name__ == "__main__":
    excel_file_path = "123.xlsx"
    excel_parser = ExcelParser(excel_file_path)  # 创建 ExcelParser 对象
    data = excel_parser.parse()  # 解析 Excel 文件
    print(data["data"])  # 打印解析后的数据
