import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.database.connection import connect
from backend.services.financial_refresh import refresh_stock_financials
from backend.services.initialize_atlas import initialize_atlas_database
from backend.services.screener import screen_stocks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class FinancialProvider:
    def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "报告期": ["2026-03-31"],
                "营业总收入同比增长率": ["10.67%"],
                "净利润同比增长率": ["35.35%"],
                "销售毛利率": ["17.07%"],
                "净资产收益率": ["1.83%"],
            }
        )


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

    def test_uses_normalized_cache_for_roe_and_revenue_growth_after_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)
            refresh_stock_financials(connection, FinancialProvider(), "000021.SZ")

            result = screen_stocks(connection)

        item = next(item for item in result["items"] if item["symbol"] == "000021.SZ")
        self.assertEqual(1.83, item["metrics"]["roe"])
        self.assertEqual(10.67, item["metrics"]["revenue_growth"])
        self.assertEqual(
            "akshare.stock_financial_abstract_ths",
            item["sources"]["roe"],
        )
        self.assertIn("roe", result["available_metrics"])
        self.assertIn("revenue_growth", result["available_metrics"])


if __name__ == "__main__":
    unittest.main()
