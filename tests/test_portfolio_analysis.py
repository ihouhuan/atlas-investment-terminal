import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.initialize_atlas import initialize_atlas_database
from backend.services.portfolio_analysis import build_portfolio_overview


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class PortfolioAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "atlas.db"
        initialize_atlas_database(self.database_path, LEGACY_ROOT)
        self.connection = connect(self.database_path)

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_builds_portfolio_risk_overview_from_latest_snapshot(self) -> None:
        overview = build_portfolio_overview(self.connection)

        self.assertEqual("2026-08-08", overview["as_of_date"])
        self.assertEqual(16389.0, overview["summary"]["market_value"])
        self.assertEqual(0.0, overview["summary"]["cash_ratio"])
        self.assertEqual(3, len(overview["positions"]))
        self.assertEqual(4, overview["risk"]["violation_count"])
        self.assertEqual("紫金矿业", overview["positions"][0]["name"])
        self.assertEqual("core", overview["positions"][0]["tier"])
        self.assertEqual(3, len(overview["industry_concentration"]))

    def test_returns_stress_scenarios_as_documented_assumptions(self) -> None:
        overview = build_portfolio_overview(self.connection)
        market_stress = overview["stress_tests"][0]

        self.assertEqual("沪深300 -20%", market_stress["name"])
        self.assertEqual("assumption", market_stress["result_type"])
        self.assertEqual(3, overview["research_integrity"]["missing_thesis_count"])
        self.assertEqual(2, overview["research_integrity"]["unconfirmed_plan_count"])
        self.assertEqual(-3277.8, market_stress["estimated_loss"])
        self.assertTrue(market_stress["source_path"].endswith("A股压力测试场景.md"))
        self.assertIn("限制", market_stress["limitations"])


if __name__ == "__main__":
    unittest.main()
