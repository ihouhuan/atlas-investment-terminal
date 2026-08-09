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
            "ATLAS MORNING INTELLIGENCE",
            "待完成行动项",
            "A 股市场状态",
            "候选股票",
            "财务指标（只读缓存）",
            "投资逻辑追踪",
            "已迁移",
            "组合概览",
        ):
            self.assertIn(expected, content)
        self.assertIn("scripts/playwright_cli.sh", content)

        wrapper = PROJECT_ROOT / "scripts" / "playwright_cli.sh"
        self.assertTrue(wrapper.is_file())
        self.assertTrue(wrapper.stat().st_mode & stat.S_IXUSR)

        workflow = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertIn("ui-smoke", workflow.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
