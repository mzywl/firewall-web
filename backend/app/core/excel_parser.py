"""
Excel 文件解析模块
"""
import openpyxl
from typing import List, Dict, Any, Tuple
import re
from datetime import datetime, date
import calendar
import logging
from dateutil.relativedelta import relativedelta
from app.core.ip_formatter import IPFormatter, PortFormatter

logger = logging.getLogger(__name__)


class ExcelParser:
    """Excel 解析器"""

    # 关键字段，用于查找真正的表头
    KEY_FIELDS = ["源IP", "目的IP", "目的端口"]

    # 字段映射：Excel表头 -> 标准英文字段名（严格以此为准, 不接受别名）
    # 设计: "源端系统-环境-用途" 解析为 source_system_name (业务系统名, 如 "vas-prod-app02")
    #      跟防火墙的 source_zone (ZoneAccessConfig.source_zone, 业务名配置) 匹配
    #      注意: 不要跟 "internal/external" 那种网络 zone 概念混
    FIELD_MAPPING = {
        "源IP": "source_ip",
        "目的IP": "dest_ip",
        "目的端口": "service",
        "源端系统-环境-用途": "source_system_name",
        "目的端系统-环境-用途": "dest_system_name",
        "动作": "action",
        "使用时间": "usage_time",
    }

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.workbook = None
        self.sheet = None

    def parse(self) -> Dict[str, Any]:
        """
        解析 Excel 文件
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

            # 4. 第一次格式化：格式化 IP 地址和端口（保留中文列头）
            formatted_v1_data = self._format_ip_addresses([dict(row) for row in data])
            logger.info(f"第一次格式化完成，共 {len(formatted_v1_data)} 行数据")

            # 5. 第二次格式化：删除示例策略 + 格式化使用时间（保留中文列头）
            formatted_v2_data = self._remove_example_policies([dict(row) for row in formatted_v1_data])
            formatted_v2_data = self._format_usage_time(formatted_v2_data)
            logger.info(f"第二次格式化完成（删除示例策略 + 格式化使用时间），剩余 {len(formatted_v2_data)} 行数据")

            # 6. 转换成英文字段名（用于保存到 Policy 表）
            normalized_data = self._normalize_field_names([dict(row) for row in formatted_v2_data])
            logger.info(f"字段名标准化完成")

            if normalized_data:
                logger.info(f"第一行数据示例: {normalized_data[0]}")

            return {
                "headers": headers,
                "data": normalized_data,          # 版本4：英文字段名数据
                "original_data": original_data,    # 版本1：原始数据（中文列头）
                "formatted_v1_data": formatted_v1_data,  # 版本2：格式化IP端口（中文列头）
                "formatted_v2_data": formatted_v2_data,  # 版本3：清洗后数据（中文列头）
                "total_rows": len(normalized_data),
                "header_row": header_row
            }
        except Exception as e:
            logger.error(f"Excel 解析失败: {str(e)}")
            raise Exception(f"Excel 解析失败: {str(e)}")
        finally:
            if self.workbook:
                self.workbook.close()

    def _find_network_policy_sheet(self):
        for sheet in self.workbook.worksheets:
            if "网络策略" in sheet.title:
                return sheet
        return self.workbook.active

    def _remove_empty_columns(self, data: List[Dict[str, Any]], headers: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
        if not data or not headers:
            return data, headers

        empty_columns = []
        for col in headers:
            is_empty = True
            for row in data:
                value = row.get(col, "")
                if value not in ("", None) and str(value).strip() != "":
                    is_empty = False
                    break
            if is_empty:
                empty_columns.append(col)

        if empty_columns:
            for row in data:
                for col in empty_columns:
                    row.pop(col, None)

        new_headers = [h for h in headers if h not in empty_columns]
        return data, new_headers

    def _find_real_header(self) -> Tuple[int, List[str]]:
        for row_idx in range(1, min(self.sheet.max_row + 1, 20)):
            row = list(self.sheet[row_idx])
            row_values = [str(cell.value).strip() if cell.value else "" for cell in row]

            if self._contains_key_fields(row_values):
                logger.info(f"找到表头行: 第 {row_idx} 行")
                return row_idx, row_values

        logger.warning("未找到包含关键字段的表头行，使用第一行")
        first_row = list(self.sheet[1])
        headers = [str(cell.value).strip() if cell.value else "" for cell in first_row]
        return 1, headers

    def _contains_key_fields(self, row_values: List[str]) -> bool:
        found_fields = set()
        for value in row_values:
            value = str(value).strip()
            if len(value) < 50:
                for key_field in self.KEY_FIELDS:
                    if key_field in value:
                        found_fields.add(key_field)

        return len(found_fields) == len(self.KEY_FIELDS)

    def _read_data(self, headers: List[str], header_row: int) -> List[Dict[str, Any]]:
        data = []
        for row_idx in range(header_row + 1, self.sheet.max_row + 1):
            row = list(self.sheet[row_idx])
            row_data = {}

            for col_idx, cell in enumerate(row):
                if col_idx < len(headers):
                    header = headers[col_idx]
                    row_data[header] = self._format_value(cell.value)

            if any(row_data.values()):
                row_data["_row_number"] = row_idx
                data.append(row_data)
        return data

    def _normalize_field_names(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_data = []
        for row in data:
            normalized_row = {}
            for key, value in row.items():
                standard_key = self.FIELD_MAPPING.get(key, key)
                normalized_row[standard_key] = value
            normalized_data.append(normalized_row)
        return normalized_data

    def _format_ip_addresses(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for row in data:
            # 依据 FIELD_MAPPING 的 Key (中文名) 统一处理
            if row.get("源IP"):
                row["源IP"] = IPFormatter.format_ip_list(str(row["源IP"]))
            if row.get("目的IP"):
                row["目的IP"] = IPFormatter.format_ip_list(str(row["目的IP"]))
            if row.get("目的端口"):
                row["目的端口"] = PortFormatter.format_port_list(str(row["目的端口"]))
        return data

    def _remove_example_policies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered_data = []
        # 对应 FIELD_MAPPING 中系统名称的中文列名
        src_key = "源端系统-环境-用途"
        dst_key = "目的端系统-环境-用途"

        for row in data:
            source_system = str(row.get(src_key, ""))
            dest_system = str(row.get(dst_key, ""))

            if "示例" in source_system and "示例" in dest_system:
                logger.info(f"过滤示例策略: 源={source_system}, 目的={dest_system}")
                continue

            filtered_data.append(row)
        return filtered_data

    def _format_usage_time(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        time_key = "使用时间"

        for row in data:
            if time_key not in row or not row[time_key]:
                continue

            time_value = str(row[time_key]).strip()
            formatted_time = '长期'

            try:
                # 规则 1: 包含 "长期"
                if '长期' in time_value:
                    formatted_time = '长期'

                # 规则 2: 包含 "X个月"
                elif '个月' in time_value:
                    months_match = re.search(r'(\d+)个月', time_value)
                    if months_match:
                        months = int(months_match.group(1))
                        future_date = date.today() + relativedelta(months=+months)
                        last_day = calendar.monthrange(future_date.year, future_date.month)[1]
                        formatted_time = f'{future_date.year}/{future_date.month:02d}/{last_day}'

                # 规则 3: 日期格式（如 2026/06/18 或 2026-06-18）
                else:
                    # 尝试匹配常见的日期字符串 YYYY-MM-DD 或 YYYY/MM/DD (允许时分秒结尾)
                    date_match = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', time_value)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        last_day = calendar.monthrange(year, month)[1]
                        formatted_time = f'{year}/{month:02d}/{last_day}'
                    else:
                        # 规则 4: 其他无法解析的情况，默认返回 "长期"
                        formatted_time = '长期'

            except Exception as e:
                logger.warning(f"时间格式化失败: {time_value}, 错误: {e}")
                formatted_time = '长期'

            row[time_key] = formatted_time

        return data

    def _format_value(self, value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, str):
            return value.strip()
        return value


if __name__ == "__main__":
    excel_file_path = "123.xlsx"
    excel_parser = ExcelParser(excel_file_path)
    data = excel_parser.parse()
    print(data["data"])