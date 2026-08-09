import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.database.connection import connect
from backend.services.initialize_atlas import initialize_atlas_database
from backend.services.financial_refresh import refresh_stock_financials
from backend.services.market_data import MarketQuote
from backend.services.stock_detail import build_stock_detail


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class Provider:
    def get_quotes(self, symbols):
        return {
            symbol: MarketQuote(symbol, "深科技", 40.85, 39.91, 0.94, 2.36, "20260807161445", "2026-08-09T00:00:00+00:00", "test", "available")
            for symbol in symbols
        }


class FinancialProvider:
    def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "报告期": ["2026-03-31"],
                "营业总收入": ["37.24亿"],
                "净利润": ["2.42亿"],
                "销售毛利率": ["17.07%"],
                "净资产收益率": ["1.83%"],
                "资产负债率": ["41.68%"],
            }
        )


class StockDetailTests(unittest.TestCase):
    def test_returns_quote_and_historical_financial_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)

            detail = build_stock_detail(connection, Provider(), "000021.SZ")

        self.assertEqual("深科技", detail["company"]["name"])
        self.assertEqual("test", detail["quote"]["source"])
        self.assertTrue(detail["financial_history"]["source_path"].endswith("stock_fundamentals.jsonl"))
        self.assertEqual(216803210.0, detail["fund_flow"]["main_inflow"])
        self.assertEqual("unavailable", detail["valuation"]["status"])

    def test_returns_normalized_financial_cache_after_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)
            refresh_stock_financials(connection, FinancialProvider(), "000021.SZ")

            detail = build_stock_detail(connection, Provider(), "000021.SZ")

        self.assertEqual("available", detail["financials"]["status"])
        self.assertEqual(
            3_724_000_000.0,
            detail["financials"]["metrics"]["total_revenue"]["value"],
        )
        self.assertEqual("2026-03-31", detail["financials"]["latest_report_date"])
