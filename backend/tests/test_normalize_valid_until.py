"""
测试 push._normalize_valid_until — 把"使用时间" 字段标准化为 generate_commands 能识别的 valid_until

接受的格式 (来自 user_modified 快照的"使用时间" 字段, 工单 16/24/25/26/27/28 实测):
  - 空 / 空白 / "长期" → "长期" (不生成 time-range/schedule)
  - "YYYY-MM-DD" / "YYYY/MM/DD" / "YYYY.MM.DD" → "YYYY-MM-DD" (生成 time-range)
  - 其它不规范 ("6个月", "测试_时间_25", ...) → 兜底 "长期"

H3C._gen_schedule_object 用 replace("/", "-") 兼容两种,
Fortigate._build_fortigate_schedule_block 用 replace("-", "/").
统一输出 "YYYY-MM-DD" 中间分隔符, 两家都兼容.
"""
from app.api.push import _normalize_valid_until


class TestNormalizeValidUntil:
    def test_long_term_passthrough(self):
        """'长期' 直接透传"""
        assert _normalize_valid_until("长期") == "长期"

    def test_empty_string_returns_long_term(self):
        """空 / 空白 / None 兜底 长期"""
        assert _normalize_valid_until("") == "长期"
        assert _normalize_valid_until("   ") == "长期"
        assert _normalize_valid_until(None) == "长期"

    def test_iso_date_format(self):
        """YYYY-MM-DD 直接透传"""
        assert _normalize_valid_until("2026-12-31") == "2026-12-31"

    def test_slash_date_format(self):
        """YYYY/MM/DD 标准化为 YYYY-MM-DD (兼容工单 24/25/26/27/28)"""
        assert _normalize_valid_until("2026/12/31") == "2026-12-31"

    def test_dot_date_format(self):
        """YYYY.MM.DD 也标准化为 YYYY-MM-DD"""
        assert _normalize_valid_until("2026.12.31") == "2026-12-31"

    def test_short_month_day_padded(self):
        """月日单位数补 0"""
        assert _normalize_valid_until("2026/1/5") == "2026-01-05"
        assert _normalize_valid_until("2026-1-5") == "2026-01-05"

    def test_invalid_format_fallback_to_long_term(self):
        """不规范格式兜底 长期, 避免推到设备时被拒绝

        实测工单 16 数据: '6个月', '测试_时间_25', '测试_时间_26'
        """
        assert _normalize_valid_until("6个月") == "长期"
        assert _normalize_valid_until("测试_时间_25") == "长期"
        assert _normalize_valid_until("测试_时间_26") == "长期"
        assert _normalize_valid_until("长期2026") == "长期"
        assert _normalize_valid_until("not-a-date") == "长期"
        assert _normalize_valid_until("2026") == "长期"  # 只有年
        assert _normalize_valid_until("2026/13") == "长期"  # 只有年月

    def test_whitespace_stripped(self):
        """首尾空白被 strip"""
        assert _normalize_valid_until("  2026/12/31  ") == "2026-12-31"
        assert _normalize_valid_until("  长期  ") == "长期"
