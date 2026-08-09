import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.financial_refresh import (
    AkshareFinancialDataProvider,
    FinancialDataError,
    normalize_financial_frame,
    refresh_stock_financials,
)


def sample_financial_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "报告期": ["2025-12-31", "2026-03-31"],
            "营业总收入": ["148.27亿", "37.24亿"],
            "营业总收入同比增长率": ["3.94%", "10.67%"],
            "净利润": ["9.30亿", "2.42亿"],
            "净利润同比增长率": ["44.33%", "35.35%"],
            "扣非净利润": [False, "1.43亿"],
            "销售毛利率": ["16.98%", "17.07%"],
            "净资产收益率": ["8.14%", "1.83%"],
            "资产负债率": ["48.24%", "41.68%"],
            "基本每股收益": ["0.5962", "0.1539"],
            "每股净资产": ["7.61", "8.49"],
            "流动比率": ["1.43", "1.40"],
            "营业周期": ["164.36", "179.75"],
        }
    )


class StubFinancialProvider:
    def __init__(self, frame=None, error=None) -> None:
        self.frame = frame if frame is not None else sample_financial_frame()
        self.error = error

    def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        if self.error is not None:
            raise self.error
        return self.frame


class FinancialRefreshTests(unittest.TestCase):
    def test_normalizes_ths_values_into_canonical_metrics(self) -> None:
        records = normalize_financial_frame(sample_financial_frame())

        latest = next(
            record
            for record in records
            if record["report_date"] == "2026-03-31"
            and record["metric_key"] == "total_revenue"
        )
        self.assertEqual(3_724_000_000.0, latest["value"])
        self.assertEqual("cny", latest["unit"])

        gross_margin = next(
            record
            for record in records
            if record["report_date"] == "2026-03-31"
            and record["metric_key"] == "gross_margin"
        )
        self.assertEqual(17.07, gross_margin["value"])
        self.assertEqual("percent", gross_margin["unit"])

        current_ratio = next(
            record
            for record in records
            if record["report_date"] == "2026-03-31"
            and record["metric_key"] == "current_ratio"
        )
        self.assertEqual(1.40, current_ratio["value"])
        self.assertEqual("times", current_ratio["unit"])

    def test_treats_false_values_as_missing_instead_of_zero(self) -> None:
        records = normalize_financial_frame(sample_financial_frame())

        missing = next(
            record
            for record in records
            if record["report_date"] == "2025-12-31"
            and record["metric_key"] == "deducted_net_profit"
        )
        self.assertIsNone(missing["value"])

    def test_refresh_persists_normalized_metrics_to_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)
            with connection:
                connection.execute(
                    "INSERT INTO stocks (symbol, name, exchange) VALUES ('000021.SZ', '深科技', 'SZ')"
                )

            result = refresh_stock_financials(
                connection,
                StubFinancialProvider(),
                "000021.SZ",
                fetched_at="2026-08-09T10:00:00+00:00",
            )

            self.assertEqual("refreshed", result["status"])
            self.assertEqual("akshare.stock_financial_abstract_ths", result["source"])
            self.assertEqual(2, result["report_periods"])
            self.assertGreater(result["metrics"], 0)
            row = connection.execute(
                """
                SELECT report_date, metric_key, value, unit
                FROM financial_metrics
                WHERE stock_id = (SELECT id FROM stocks WHERE symbol = '000021.SZ')
                  AND metric_key = 'total_revenue'
                ORDER BY report_date DESC
                LIMIT 1
                """
            ).fetchone()
            self.assertEqual("2026-03-31", row["report_date"])
            self.assertEqual(3_724_000_000.0, row["value"])
            self.assertEqual("cny", row["unit"])

    def test_refresh_is_idempotent_and_updates_existing_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)
            with connection:
                connection.execute(
                    "INSERT INTO stocks (symbol, name, exchange) VALUES ('000021.SZ', '深科技', 'SZ')"
                )

            refresh_stock_financials(connection, StubFinancialProvider(), "000021.SZ")
            first_count = connection.execute(
                "SELECT COUNT(*) FROM financial_metrics"
            ).fetchone()[0]

            changed_frame = sample_financial_frame().copy()
            changed_frame.loc[changed_frame["报告期"] == "2026-03-31", "销售毛利率"] = "18.50%"
            refresh_stock_financials(connection, StubFinancialProvider(changed_frame), "000021.SZ")
            second_count = connection.execute(
                "SELECT COUNT(*) FROM financial_metrics"
            ).fetchone()[0]
            gross_margin = connection.execute(
                """
                SELECT value FROM financial_metrics
                WHERE stock_id = (SELECT id FROM stocks WHERE symbol = '000021.SZ')
                  AND metric_key = 'gross_margin'
                  AND report_date = '2026-03-31'
                """
            ).fetchone()[0]

            self.assertEqual(first_count, second_count)
            self.assertEqual(18.50, gross_margin)

    def test_unknown_symbol_raises_lookup_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)

            with self.assertRaises(LookupError):
                refresh_stock_financials(
                    connection, StubFinancialProvider(), "000021.SZ"
                )

    def test_provider_failure_propagates_financial_data_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)
            with connection:
                connection.execute(
                    "INSERT INTO stocks (symbol, name, exchange) VALUES ('000021.SZ', '深科技', 'SZ')"
                )

            with self.assertRaises(FinancialDataError):
                refresh_stock_financials(
                    connection,
                    StubFinancialProvider(error=FinancialDataError("upstream unavailable")),
                    "000021.SZ",
                )

    def test_akshare_provider_passes_six_digit_code_to_fetch_function(self) -> None:
        calls = []

        def record_fetch(symbol: str) -> pd.DataFrame:
            calls.append(symbol)
            return sample_financial_frame()

        provider = AkshareFinancialDataProvider(fetch_abstract=record_fetch)
        provider.get_financial_abstract("000021.SZ")

        self.assertEqual(["000021"], calls)

    def test_akshare_provider_rejects_empty_result(self) -> None:
        provider = AkshareFinancialDataProvider(
            fetch_abstract=lambda symbol: pd.DataFrame()
        )

        with self.assertRaises(FinancialDataError):
            provider.get_financial_abstract("000021.SZ")


if __name__ == "__main__":
    unittest.main()
