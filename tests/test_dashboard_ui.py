import unittest

from app.dashboard.ui import (
    change_tone,
    humanize_amount,
    humanize_datetime,
    status_label,
)


class DashboardUITests(unittest.TestCase):
    def test_humanize_amount_uses_billion_and_ten_thousand_units(self) -> None:
        self.assertEqual("37.24 亿", humanize_amount(3_724_000_000.0))
        self.assertEqual("1.23 万", humanize_amount(12_345.0))
        self.assertEqual("999.00 元", humanize_amount(999.0))
        self.assertEqual("数据不可用", humanize_amount(None))

    def test_humanize_datetime_normalizes_iso_and_tencent_stamps(self) -> None:
        self.assertIn("08-09", humanize_datetime("2026-08-09T08:00:00+00:00"))
        self.assertIn("08-07 16:14", humanize_datetime("20260807161445"))
        self.assertEqual("未提供", humanize_datetime(None))

    def test_status_label_translates_core_states(self) -> None:
        self.assertEqual("可用", status_label("available"))
        self.assertEqual("历史缓存", status_label("cached"))
        self.assertEqual("不可用", status_label("unavailable"))
        self.assertEqual("unknown", status_label("unknown"))

    def test_change_tone_maps_sign_to_display_tone(self) -> None:
        self.assertEqual("up", change_tone(1.2))
        self.assertEqual("down", change_tone(-0.3))
        self.assertEqual("neutral", change_tone(0))
        self.assertEqual("neutral", change_tone(None))


if __name__ == "__main__":
    unittest.main()
