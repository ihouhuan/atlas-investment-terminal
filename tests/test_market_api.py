import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.services.financial_refresh import FinancialDataError
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


def sample_financial_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "报告期": ["2026-03-31"],
            "营业总收入": ["37.24亿"],
            "净利润": ["2.42亿"],
            "净利润同比增长率": ["35.35%"],
            "销售毛利率": ["17.07%"],
            "净资产收益率": ["1.83%"],
            "资产负债率": ["41.68%"],
        }
    )


class StubFinancialProvider:
    def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        return sample_financial_frame()


class FailingFinancialProvider:
    def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        raise FinancialDataError("upstream unavailable")


class StubStockMetadataProvider:
    def get_stock_metadata(self, symbol: str) -> dict:
        return {
            "name": "浦发银行",
            "exchange": "SH",
            "sector": None,
            "industry": "银行",
        }


class StubMarketBreadthProvider:
    def get_breadth(self) -> dict:
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


class MarketApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "atlas.db"
        initialize_atlas_database(self.database_path, LEGACY_ROOT)
        self.client = TestClient(
            create_app(
                self.database_path,
                StubMarketDataProvider(),
                StubFinancialProvider(),
                StubStockMetadataProvider(),
                StubMarketBreadthProvider(),
            )
        )

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_directory.cleanup()

    def test_market_overview_returns_index_quotes_and_available_breadth(self) -> None:
        response = self.client.get("/api/v1/market/overview")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(3, len(body["indices"]))
        self.assertEqual("沪深300", body["indices"][0]["name"])
        self.assertEqual("test_provider", body["indices"][0]["source"])
        self.assertEqual("available", body["breadth"]["status"])
        self.assertEqual(4000, body["breadth"]["advancers"])
        self.assertEqual(12345.67, body["breadth"]["turnover_yi"])

    def test_watchlist_returns_database_stocks_with_quote_provenance(self) -> None:
        response = self.client.get("/api/v1/watchlist?limit=2")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(2, len(body["items"]))
        self.assertEqual(87, body["total"])
        self.assertEqual("test_provider", body["items"][0]["quote"]["source"])
        self.assertEqual("legacy_watchlist", body["items"][0]["category"])

    def test_portfolio_overview_returns_rule_checks_and_stress_assumptions(self) -> None:
        response = self.client.get("/api/v1/portfolio/overview")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(3, len(body["positions"]))
        self.assertEqual(4, body["risk"]["violation_count"])
        self.assertEqual("assumption", body["stress_tests"][0]["result_type"])

    def test_morning_brief_snapshot_compares_risk_and_research_todo_changes(self) -> None:
        initial_delta = self.client.get("/api/v1/morning-brief/delta")
        self.assertEqual(200, initial_delta.status_code)
        self.assertEqual("unavailable", initial_delta.json()["status"])

        first_snapshot = self.client.post("/api/v1/morning-brief/snapshots")
        self.assertEqual(201, first_snapshot.status_code)
        first_delta = self.client.get("/api/v1/morning-brief/delta")
        self.assertEqual("baseline", first_delta.json()["status"])

        second_snapshot = self.client.post("/api/v1/morning-brief/snapshots")
        self.assertEqual(201, second_snapshot.status_code)
        second_delta = self.client.get("/api/v1/morning-brief/delta")
        body = second_delta.json()
        self.assertEqual("available", body["status"])
        self.assertEqual(0, body["changes"]["risk_violation_count"])
        self.assertEqual(0, body["changes"]["missing_thesis_count"])
        self.assertEqual(0, body["changes"]["unconfirmed_plan_count"])

    def test_morning_brief_history_supports_comparing_selected_snapshots(self) -> None:
        first_snapshot = self.client.post("/api/v1/morning-brief/snapshots").json()
        second_snapshot = self.client.post("/api/v1/morning-brief/snapshots").json()

        history = self.client.get("/api/v1/morning-brief/snapshots")
        self.assertEqual(200, history.status_code)
        self.assertEqual(2, history.json()["total"])
        self.assertEqual(second_snapshot["id"], history.json()["items"][0]["id"])

        comparison = self.client.get(
            "/api/v1/morning-brief/delta?current_id={}&previous_id={}".format(
                second_snapshot["id"], first_snapshot["id"]
            )
        )
        self.assertEqual(200, comparison.status_code)
        self.assertEqual(second_snapshot["id"], comparison.json()["current"]["id"])
        self.assertEqual(first_snapshot["id"], comparison.json()["previous"]["id"])

    def test_morning_brief_snapshot_preserves_optional_research_conclusion(self) -> None:
        response = self.client.post(
            "/api/v1/morning-brief/snapshots",
            json={"research_conclusion": "盈利预期仍待验证，维持风险优先的研究节奏。"},
        )

        self.assertEqual(201, response.status_code)
        self.assertEqual("盈利预期仍待验证，维持风险优先的研究节奏。", response.json()["research_conclusion"])
        history = self.client.get("/api/v1/morning-brief/snapshots")
        self.assertEqual("盈利预期仍待验证，维持风险优先的研究节奏。", history.json()["items"][0]["research_conclusion"])

    def test_morning_brief_snapshot_can_be_marked_reviewed_with_date(self) -> None:
        snapshot = self.client.post("/api/v1/morning-brief/snapshots").json()

        response = self.client.patch(
            "/api/v1/morning-brief/snapshots/{}/review".format(snapshot["id"]),
            json={"reviewed": True, "reviewed_at": "2026-08-09"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("reviewed", response.json()["review_status"])
        self.assertEqual("2026-08-09", response.json()["reviewed_at"])
        history = self.client.get("/api/v1/morning-brief/snapshots")
        self.assertEqual("reviewed", history.json()["items"][0]["review_status"])

    def test_reviewed_morning_brief_stores_notes_and_linked_follow_up_action(self) -> None:
        snapshot = self.client.post("/api/v1/morning-brief/snapshots").json()
        self.client.patch(
            "/api/v1/morning-brief/snapshots/{}/review".format(snapshot["id"]),
            json={"reviewed": True, "review_notes": "风险项已分配给本周复盘。"},
        )

        action = self.client.post(
            "/api/v1/morning-brief/snapshots/{}/actions".format(snapshot["id"]),
            json={"action_text": "核对限价卖出是否执行", "decision_legacy_key": "007-600693.SH"},
        )

        self.assertEqual(201, action.status_code)
        self.assertEqual("007-600693.SH", action.json()["decision_legacy_key"])
        actions = self.client.get("/api/v1/morning-brief/snapshots/{}/actions".format(snapshot["id"])).json()
        self.assertEqual("open", actions["items"][0]["status"])
        completed = self.client.patch(
            "/api/v1/morning-brief/snapshots/{}/actions/{}".format(snapshot["id"], action.json()["id"]),
            json={"completed": True},
        )
        self.assertEqual("completed", completed.json()["status"])

    def test_open_follow_up_actions_are_aggregated_with_snapshot_context(self) -> None:
        snapshot = self.client.post("/api/v1/morning-brief/snapshots").json()
        self.client.patch(
            "/api/v1/morning-brief/snapshots/{}/review".format(snapshot["id"]),
            json={"reviewed": True},
        )
        self.client.post(
            "/api/v1/morning-brief/snapshots/{}/actions".format(snapshot["id"]),
            json={"action_text": "复核仓位上限", "decision_legacy_key": "007-600693.SH", "due_date": "2026-08-08", "priority": "high"},
        )

        response = self.client.get("/api/v1/morning-brief/actions?status=open")

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.json()["total"])
        self.assertEqual(snapshot["id"], response.json()["items"][0]["snapshot_id"])
        self.assertEqual("007-600693.SH", response.json()["items"][0]["decision_legacy_key"])
        self.assertEqual("high", response.json()["items"][0]["priority"])
        self.assertTrue(response.json()["items"][0]["is_overdue"])

    def test_action_summary_filters_today_and_reports_completion_rate(self) -> None:
        snapshot = self.client.post("/api/v1/morning-brief/snapshots").json()
        self.client.patch("/api/v1/morning-brief/snapshots/{}/review".format(snapshot["id"]), json={"reviewed": True})
        today_action = self.client.post(
            "/api/v1/morning-brief/snapshots/{}/actions".format(snapshot["id"]),
            json={"action_text": "今日核对", "due_date": date.today().isoformat()},
        ).json()
        self.client.post(
            "/api/v1/morning-brief/snapshots/{}/actions".format(snapshot["id"]),
            json={"action_text": "后续核对", "due_date": (date.today() + timedelta(days=8)).isoformat()},
        )
        self.client.patch(
            "/api/v1/morning-brief/snapshots/{}/actions/{}".format(snapshot["id"], today_action["id"]),
            json={"completed": True},
        )

        response = self.client.get("/api/v1/morning-brief/actions?status=open&due_window=today")

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.json()["total"])
        self.assertEqual(2, response.json()["summary"]["total"])
        self.assertEqual(50.0, response.json()["summary"]["completion_rate"])

    def test_action_trend_reports_recent_completion_rate(self) -> None:
        snapshot = self.client.post("/api/v1/morning-brief/snapshots").json()
        self.client.patch("/api/v1/morning-brief/snapshots/{}/review".format(snapshot["id"]), json={"reviewed": True})
        action = self.client.post(
            "/api/v1/morning-brief/snapshots/{}/actions".format(snapshot["id"]),
            json={"action_text": "完成趋势测试"},
        ).json()
        self.client.patch(
            "/api/v1/morning-brief/snapshots/{}/actions/{}".format(snapshot["id"], action["id"]),
            json={"completed": True},
        )

        response = self.client.get("/api/v1/morning-brief/actions/trend?days=7")

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.json()["summary"]["completed"])
        self.assertEqual(100.0, response.json()["summary"]["completion_rate"])

    def test_screener_returns_historical_candidates_with_provenance(self) -> None:
        response = self.client.get("/api/v1/screener?max_pe_ttm=30&min_profit_growth=20")

        self.assertEqual(200, response.status_code)
        body = response.json()
        candidate = next(item for item in body["items"] if item["symbol"] == "002475.SZ")
        self.assertEqual("historical_snapshot", body["data_status"])
        self.assertEqual(30, body["filters"]["max_pe_ttm"])
        self.assertEqual("legacy", candidate["sources"]["profit_growth"])

    def test_refreshes_single_stock_financials_and_returns_normalized_cache(self) -> None:
        response = self.client.post("/api/v1/stocks/000021.SZ/financials/refresh")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("refreshed", body["status"])
        self.assertEqual("000021.SZ", body["symbol"])
        self.assertEqual("akshare.stock_financial_abstract_ths", body["source"])
        self.assertGreater(body["metrics"], 0)

        detail = self.client.get("/api/v1/stocks/000021.SZ")
        self.assertEqual(200, detail.status_code)
        financials = detail.json()["financials"]
        self.assertEqual("available", financials["status"])
        self.assertEqual(
            3_724_000_000.0,
            financials["metrics"]["total_revenue"]["value"],
        )
        self.assertEqual("2026-03-31", financials["latest_report_date"])

    def test_creates_new_stock_master_record_and_exposes_detail(self) -> None:
        response = self.client.post(
            "/api/v1/stocks",
            json={"symbol": "600000.SH", "name": "浦发银行"},
        )

        self.assertEqual(201, response.status_code)
        body = response.json()
        self.assertEqual("created", body["status"])
        self.assertEqual("SH", body["stock"]["exchange"])
        self.assertEqual("银行", body["stock"]["industry"])

        detail = self.client.get("/api/v1/stocks/600000.SH")
        self.assertEqual(200, detail.status_code)
        self.assertEqual("浦发银行", detail.json()["company"]["name"])

        refresh = self.client.post("/api/v1/stocks/600000.SH/financials/refresh")
        self.assertEqual(200, refresh.status_code)

    def test_updates_existing_stock_master_record_without_duplicate(self) -> None:
        response = self.client.post(
            "/api/v1/stocks",
            json={"symbol": "000021.SZ", "name": "深科技"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("updated", response.json()["status"])
        watchlist = self.client.get("/api/v1/watchlist?limit=200")
        self.assertEqual(87, watchlist.json()["total"])

    def test_financial_refresh_returns_404_for_unknown_symbol(self) -> None:
        response = self.client.post("/api/v1/stocks/999999.SZ/financials/refresh")

        self.assertEqual(404, response.status_code)

    def test_bulk_financial_refresh_refreshes_selected_symbols(self) -> None:
        response = self.client.post(
            "/api/v1/stocks/financials/refresh?symbols=000021.SZ,601899.SH"
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("completed", body["status"])
        self.assertEqual(2, body["total"])
        self.assertEqual(2, body["refreshed"])
        self.assertEqual(0, body["failed"])

    def test_financial_refresh_returns_502_when_upstream_fails(self) -> None:
        client = TestClient(
            create_app(
                self.database_path,
                StubMarketDataProvider(),
                FailingFinancialProvider(),
                StubStockMetadataProvider(),
                StubMarketBreadthProvider(),
            )
        )
        self.addCleanup(client.close)

        response = client.post("/api/v1/stocks/000021.SZ/financials/refresh")

        self.assertEqual(502, response.status_code)
        self.assertEqual("upstream unavailable", response.json()["detail"])

    def test_stock_detail_returns_404_for_unknown_symbol(self) -> None:
        response = self.client.get("/api/v1/stocks/999999.SZ")

        self.assertEqual(404, response.status_code)

    def test_thesis_overview_exposes_missing_definitions(self) -> None:
        response = self.client.get("/api/v1/thesis")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(3, body["total"])
        self.assertEqual(3, body["needs_definition_count"])
        self.assertEqual("needs_definition", body["items"][0]["status"])

    def test_creates_a_manual_thesis_version_without_replacing_history(self) -> None:
        response = self.client.post(
            "/api/v1/thesis/versions",
            json={
                "symbol": "601899.SH",
                "thesis": "铜金产量增长支持自由现金流改善",
                "validation_metrics": "铜价与产量季度跟踪",
                "invalid_conditions": "产量持续不及预期",
                "review_date": "2026-11-08",
                "source_note": "首次手动记录",
            },
        )

        self.assertEqual(201, response.status_code)
        self.assertEqual("user_entry", response.json()["entry_source"])
        overview = self.client.get("/api/v1/thesis").json()
        item = next(record for record in overview["items"] if record["symbol"] == "601899.SH")
        self.assertEqual("defined", item["status"])
        self.assertEqual("铜价与产量季度跟踪", item["validation_metrics"])
        history = self.client.get("/api/v1/thesis/601899.SH/versions")
        self.assertEqual(200, history.status_code)
        self.assertEqual("首次手动记录", history.json()["items"][0]["source_note"])

    def test_decision_journal_returns_import_quality_status(self) -> None:
        response = self.client.get("/api/v1/decisions")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(7, body["total"])
        self.assertEqual(0, body["incomplete_import_count"])
        self.assertEqual("planned_record", next(item for item in body["items"] if item["legacy_key"] == "007-600693.SH")["record_status"])

    def test_appends_manual_decision_updates(self) -> None:
        response = self.client.post(
            "/api/v1/decisions/007-600693.SH/updates",
            json={"event_type": "not_executed", "execution_date": "2026-08-11", "actual_result": "未成交", "review_notes": "挂单当日未执行"},
        )

        self.assertEqual(201, response.status_code)
        history = self.client.get("/api/v1/decisions/007-600693.SH/updates")
        self.assertEqual(200, history.status_code)
        self.assertEqual("未成交", history.json()["items"][0]["actual_result"])


if __name__ == "__main__":
    unittest.main()
