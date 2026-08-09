import stat
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SchedulingScriptTests(unittest.TestCase):
    def test_daily_scripts_are_executable_and_configured(self) -> None:
        run_script = PROJECT_ROOT / "scripts" / "run_daily.sh"
        install_script = PROJECT_ROOT / "scripts" / "install_daily_launchagent.sh"

        self.assertTrue(run_script.is_file())
        self.assertTrue(install_script.is_file())
        self.assertTrue(run_script.stat().st_mode & stat.S_IXUSR)
        self.assertTrue(install_script.stat().st_mode & stat.S_IXUSR)
        self.assertIn(
            "--financial-scope watchlist",
            run_script.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "com.atlas.daily",
            install_script.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
