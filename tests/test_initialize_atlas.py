import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.initialize_atlas import initialize_atlas_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class InitializeAtlasTests(unittest.TestCase):
    def test_creates_database_with_canonical_rules_and_legacy_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"

            result = initialize_atlas_database(database_path, LEGACY_ROOT)

            connection = connect(database_path)
            self.addCleanup(connection.close)
            active_budget_count = connection.execute(
                "SELECT COUNT(*) FROM risk_budget_versions WHERE is_active = 1"
            ).fetchone()[0]
            position_count = connection.execute(
                "SELECT COUNT(*) FROM portfolio_positions"
            ).fetchone()[0]
            stock = connection.execute(
                "SELECT sector, industry FROM stocks WHERE symbol = '601899.SH'"
            ).fetchone()

            self.assertEqual(3, result["positions"])
            self.assertEqual(1, result["risk_budget_versions"])
            self.assertEqual(1, active_budget_count)
            self.assertEqual(3, position_count)
            self.assertEqual("贵金属/有色金属（铜金）", stock["sector"])
            self.assertEqual("小金属", stock["industry"])


if __name__ == "__main__":
    unittest.main()
