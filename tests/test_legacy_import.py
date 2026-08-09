import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.legacy_import import import_legacy_atlas


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class LegacyImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection = connect(Path(self.temporary_directory.name) / "atlas.db")
        initialize_database(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_imports_legacy_assets_with_provenance(self) -> None:
        result = import_legacy_atlas(self.connection, LEGACY_ROOT)

        self.assertEqual(3, result["positions"])
        self.assertEqual(1, result["investor_profiles"])
        self.assertEqual(7, result["decisions"])

        snapshot = self.connection.execute(
            "SELECT as_of_date, source_path FROM portfolio_snapshots"
        ).fetchone()
        decision = self.connection.execute(
            "SELECT symbol, source_path FROM decisions WHERE legacy_key = '001'"
        ).fetchone()

        self.assertEqual("2026-08-08", snapshot["as_of_date"])
        self.assertTrue(snapshot["source_path"].endswith("portfolio/portfolio.json"))
        self.assertEqual("NVDA", decision["symbol"])
        self.assertTrue(decision["source_path"].endswith("决策日志/决策日志.md"))
        planned_sale = self.connection.execute(
            """
            SELECT decision_date, symbol, action, price_text, position_text, thesis, invalid_conditions
            FROM decisions WHERE legacy_key = '007-600693.SH'
            """
        ).fetchone()
        self.assertEqual("2026-08-08", planned_sale["decision_date"])
        self.assertEqual("600693.SH", planned_sale["symbol"])
        self.assertEqual("计划挂单卖出（限价单）", planned_sale["action"])
        self.assertEqual("¥10.30", planned_sale["price_text"])
        self.assertEqual("700 股", planned_sale["position_text"])
        self.assertEqual("题材股 + 零售复苏", planned_sale["thesis"])
        self.assertEqual("跌穿 ¥9.00 + 板块轮动利空", planned_sale["invalid_conditions"])

    def test_import_is_idempotent(self) -> None:
        import_legacy_atlas(self.connection, LEGACY_ROOT)
        result = import_legacy_atlas(self.connection, LEGACY_ROOT)

        self.assertEqual({"positions": 0, "investor_profiles": 0, "decisions": 0}, result)
        self.assertEqual(
            3,
            self.connection.execute("SELECT COUNT(*) FROM portfolio_positions").fetchone()[0],
        )
        self.assertEqual(
            1,
            self.connection.execute("SELECT COUNT(*) FROM investor_profiles").fetchone()[0],
        )
        self.assertEqual(
            7,
            self.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0],
        )


if __name__ == "__main__":
    unittest.main()
