import stat
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class UISmokeScriptTests(unittest.TestCase):
    def test_ui_smoke_script_is_executable_and_covers_key_pages(self) -> None:
        script = PROJECT_ROOT / "scripts" / "ui_smoke.sh"

        self.assertTrue(script.is_file())
        self.assertTrue(script.stat().st_mode & stat.S_IXUSR)
        content = script.read_text(encoding="utf-8")
        for expected in (
            "晨报",
            "A 股市场状态",
            "选股中心",
            "财务指标（只读缓存）",
            "投资逻辑追踪",
            "决策日志",
            "组合与风险",
        ):
            self.assertIn(expected, content)


if __name__ == "__main__":
    unittest.main()
