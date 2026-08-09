import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.database.connection import connect
from backend.services.daily_run import main as daily_run_cli_main, run_daily
from backend.services.initialize_atlas import initialize_atlas_database
from backend.services.market_data import MarketQuote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class StubMarketDataProvider:
    def get_quotes(self, symbols):
        return {
            symbol: MarketQuote(
                symbol=symbol,
                name="测试标的",
                price=100.0,
                previous_close=99.0,
                change=1.0,
                change_pct=1.01,
                observed_at="20260809103000",
                fetched_at="2026-08-09T10:30:00+00:00",
                source="test_provider",
                status="available",
            )
            for symbol in symbols
        }


class StubBreadthProvider:
    def get_breadth(self):
        return {
            "status": "available",
            "advancers": 4000,
            "decliners": 1000,
            "limit_up": 50,
            "limit_down": 10,
            "turnover_yi": 12345.67,
            "source": "stub_breadth",
            "as_of": "2026-08-09T10:00:00+00:00",
        }


class StubFinancialProvider:
    def get_financial_abstract(self, symbol):
        return pd.DataFrame(
            {
                "报告期": ["2026-03-31"],
                "营业总收入": ["37.24亿"],
                "净利润": ["2.42亿"],
                "销售毛利率": ["17.07%"],
                "净资产收益率": ["1.83%"],
            }
        )


class DailyRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "atlas.db"
        initialize_atlas_database(self.database_path, LEGACY_ROOT)
        self.connection = connect(self.database_path)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.temporary_directory.cleanup)

    def test_run_daily_writes_report_snapshot_and_refreshes_watchlist(self) -> None:
        output_dir = Path(self.temporary_directory.name) / "reports"
        run_at = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)

        manifest = run_daily(
            self.connection,
            StubMarketDataProvider(),
            StubBreadthProvider(),
            StubFinancialProvider(),
            output_dir,
            financial_scope="watchlist",
            run_id="test-run",
            now=run_at,
        )

        self.assertEqual("completed", manifest["status"])
        self.assertEqual(1, manifest["morning_brief_snapshot_id"])
        self.assertGreater(manifest["financial_refresh"]["refreshed"], 0)
        report_path = Path(manifest["report_path"])
        self.assertTrue(report_path.is_file())
        self.assertIn("# Atlas 晨报", report_path.read_text(encoding="utf-8"))
        snapshot_count = self.connection.execute(
            "SELECT COUNT(*) FROM morning_brief_snapshots"
        ).fetchone()[0]
        self.assertEqual(1, snapshot_count)

    def test_run_daily_skips_financial_refresh_when_scope_is_none(self) -> None:
        output_dir = Path(self.temporary_directory.name) / "reports"

        manifest = run_daily(
            self.connection,
            StubMarketDataProvider(),
            StubBreadthProvider(),
            StubFinancialProvider(),
            output_dir,
            financial_scope="none",
            run_id="test-run-none",
        )

        self.assertIsNone(manifest["financial_refresh"])
        metric_count = self.connection.execute(
            "SELECT COUNT(*) FROM financial_metrics"
        ).fetchone()[0]
        self.assertEqual(0, metric_count)

    def test_cli_prints_machine_readable_manifest(self) -> None:
        output_dir = Path(self.temporary_directory.name) / "reports"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = daily_run_cli_main(
                [
                    "--database",
                    str(self.database_path),
                    "--output-dir",
                    str(output_dir),
                    "--run-id",
                    "cli-run",
                ],
                market_provider=StubMarketDataProvider(),
                breadth_provider=StubBreadthProvider(),
                financial_provider=StubFinancialProvider(),
            )
        manifest = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual("cli-run", manifest["run_id"])
        self.assertTrue(Path(manifest["report_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
