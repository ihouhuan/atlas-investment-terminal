import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.initialize_atlas import initialize_atlas_database
from backend.services.screener import screen_stocks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class ScreenerTests(unittest.TestCase):
    def test_filters_historical_fundamental_and_valuation_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)

            result = screen_stocks(connection, max_pe_ttm=30, min_profit_growth=20)

        symbols = [item["symbol"] for item in result["items"]]
        self.assertIn("002475.SZ", symbols)
        self.assertNotIn("000021.SZ", symbols)
        self.assertNotIn("600110.SH", symbols)
        self.assertEqual("historical_snapshot", result["data_status"])
        self.assertEqual("legacy", next(item for item in result["items"] if item["symbol"] == "002475.SZ")["sources"]["profit_growth"])


if __name__ == "__main__":
    unittest.main()
