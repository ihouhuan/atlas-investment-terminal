import unittest
from pathlib import Path

from app.dashboard.main import market_index_rows
from app.pages.decision_journal import decision_rows
from app.pages.screener import screener_rows
from app.pages.stock_detail import (
    financial_history_rows,
    financial_metric_rows,
    valuation_rows,
)
from app.pages.thesis import thesis_rows
from app.pages.morning_brief import (
    brief_delta_rows,
    brief_history_rows,
    morning_brief_comparison_markdown,
    morning_brief_markdown,
    priority_action_rows,
    execution_alert,
)
from app.pages.portfolio_risk import portfolio_position_rows


class DashboardPresentationTests(unittest.TestCase):
    def test_dashboard_source_avoids_deprecated_streamlit_width_argument(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        offenders = [
            str(path)
            for path in (project_root / "app").rglob("*.py")
            if "use_container_width" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual([], offenders)

    def test_warns_when_completion_rate_stays_low_across_two_windows(self) -> None:
        alert = execution_alert(
            {"summary": {"created": 3, "completion_rate": 33.3}},
            {"summary": {"created": 6, "completion_rate": 40.0}},
        )

        self.assertEqual("warning", alert["status"])
        self.assertIn("执行力提醒", alert["message"])

    def test_selects_overdue_and_high_priority_actions_for_today(self) -> None:
        rows = priority_action_rows(
            {
                "items": [
                    {"action_text": "逾期事项", "snapshot_id": 1, "decision_legacy_key": None, "priority": "low", "due_date": "2026-08-08", "is_overdue": True},
                    {"action_text": "高优先事项", "snapshot_id": 2, "decision_legacy_key": "007", "priority": "high", "due_date": None, "is_overdue": False},
                    {"action_text": "普通事项", "snapshot_id": 3, "decision_legacy_key": None, "priority": "normal", "due_date": None, "is_overdue": False},
                ]
            }
        )

        self.assertEqual(["逾期事项", "高优先事项"], [row["行动项"] for row in rows])

    def test_generates_selected_morning_brief_comparison_markdown(self) -> None:
        content = morning_brief_comparison_markdown(
            {
                "status": "available",
                "current": {"id": 8, "created_at": "2026-08-09T08:00:00+00:00", "research_conclusion": "耐心等待盈利验证。"},
                "previous": {"id": 3, "created_at": "2026-08-08T08:00:00+00:00", "research_conclusion": "关注风险预算。"},
                "changes": {
                    "risk_violation_count": 2,
                    "missing_thesis_count": 0,
                    "unconfirmed_plan_count": -1,
                },
            }
        )

        self.assertIn("# Atlas 晨报差异复盘", content)
        self.assertIn("当前晨报：#8", content)
        self.assertIn("对比晨报：#3", content)
        self.assertIn("风险预算违规：新增 2 项", content)
        self.assertIn("当前结论：耐心等待盈利验证。", content)

    def test_formats_brief_delta_with_new_risks_and_todos(self) -> None:
        rows = brief_delta_rows(
            {
                "status": "available",
                "changes": {
                    "risk_violation_count": 2,
                    "missing_thesis_count": 1,
                    "unconfirmed_plan_count": -1,
                },
            }
        )

        self.assertEqual("新增 2 项", rows[0]["变化"])
        self.assertEqual("新增 1 项", rows[1]["变化"])
        self.assertEqual("减少 1 项", rows[2]["变化"])

    def test_formats_local_morning_brief_history_for_review(self) -> None:
        rows = brief_history_rows(
            {
                "items": [
                    {
                        "id": 8,
                        "created_at": "2026-08-09T08:00:00+00:00",
                        "risk_violation_count": 4,
                        "missing_thesis_count": 3,
                        "unconfirmed_plan_count": 2,
                        "research_conclusion": "耐心等待盈利验证。",
                        "review_status": "reviewed",
                        "reviewed_at": "2026-08-09",
                    }
                ]
            }
        )

        self.assertEqual("#8", rows[0]["快照"])
        self.assertEqual(4, rows[0]["风险预算违规"])
        self.assertEqual("耐心等待盈利验证。", rows[0]["当日研究结论"])
        self.assertEqual("已复盘", rows[0]["复盘状态"])
        self.assertEqual("2026-08-09", rows[0]["复盘日期"])

    def test_generates_morning_brief_markdown_with_sources(self) -> None:
        content = morning_brief_markdown(
            {"indices": [{"name": "沪深300", "price": 4000, "change_pct": 1.2, "source": "test", "observed_at": "now"}]},
            {"research_integrity": {"missing_thesis_count": 3, "unconfirmed_plan_count": 2}, "risk": {"violation_count": 4}},
            {"items": [{"name": "测试", "symbol": "000001.SZ", "sector": "银行"}]},
            {"status": "available", "changes": {"risk_violation_count": 2, "missing_thesis_count": 0, "unconfirmed_plan_count": -1}},
        )
        self.assertIn("沪深300：4000.00", content)
        self.assertIn("缺少 Thesis：3", content)
        self.assertIn("## 风险变化摘要", content)
        self.assertIn("风险预算违规：新增 2 项", content)
        self.assertIn("测试（000001.SZ）", content)
    def test_formats_unavailable_market_data_without_displaying_a_fake_price(self) -> None:
        rows = market_index_rows(
            {
                "indices": [
                    {
                        "name": "沪深300",
                        "price": None,
                        "change_pct": None,
                        "status": "unavailable",
                        "source": "none",
                        "observed_at": None,
                    }
                ]
            }
        )

        self.assertEqual("数据不可用", rows[0]["最新价"])
        self.assertEqual("数据不可用", rows[0]["涨跌幅"])
        self.assertEqual("none", rows[0]["来源"])

    def test_formats_screener_rows_with_metric_provenance(self) -> None:
        rows = screener_rows(
            {
                "items": [
                    {
                        "symbol": "002475.SZ",
                        "name": "立讯精密",
                        "sector": "果链/消费电子",
                        "metrics": {"pe_ttm": 25.57, "profit_growth": 20.24, "gross_margin": None},
                        "sources": {"pe_ttm": "tencent", "profit_growth": "legacy"},
                    }
                ]
            }
        )

        self.assertEqual("25.57", rows[0]["PE TTM"])
        self.assertEqual("20.24%", rows[0]["净利润同比"])
        self.assertEqual("数据不可用", rows[0]["毛利率"])
        self.assertEqual("tencent / legacy", rows[0]["指标来源"])

    def test_formats_screener_rows_with_normalized_roe_and_revenue_growth(self) -> None:
        rows = screener_rows(
            {
                "items": [
                    {
                        "symbol": "000021.SZ",
                        "name": "深科技",
                        "sector": "果链/消费电子",
                        "metrics": {"roe": 1.83, "revenue_growth": 10.67},
                        "sources": {"roe": "akshare.stock_financial_abstract_ths", "revenue_growth": "akshare.stock_financial_abstract_ths"},
                    }
                ]
            }
        )

        self.assertEqual("1.83%", rows[0]["ROE"])
        self.assertEqual("10.67%", rows[0]["营收同比"])
        self.assertEqual("akshare.stock_financial_abstract_ths", rows[0]["指标来源"])

    def test_formats_available_market_data_with_source(self) -> None:
        rows = market_index_rows(
            {
                "indices": [
                    {
                        "name": "沪深300",
                        "price": 4000.12,
                        "change_pct": 1.23,
                        "status": "available",
                        "source": "tencent_qt.gtimg.cn",
                        "observed_at": "20260809103000",
                    }
                ]
            }
        )

        self.assertEqual("4,000.12", rows[0]["最新价"])
        self.assertEqual("+1.23%", rows[0]["涨跌幅"])
        self.assertEqual("tencent_qt.gtimg.cn", rows[0]["来源"])

    def test_formats_portfolio_weights_and_pnl_for_display(self) -> None:
        rows = portfolio_position_rows(
            {
                "positions": [
                    {
                        "name": "紫金矿业",
                        "symbol": "601899.SH",
                        "market_value": 7030.0,
                        "weight": 0.4289,
                        "pnl": -45.27,
                        "tier": "core",
                    }
                ]
            }
        )

        self.assertEqual("42.89%", rows[0]["仓位"])
        self.assertEqual("-45.27", rows[0]["浮动盈亏"])
        self.assertEqual("core", rows[0]["仓位层级"])

    def test_formats_thesis_rows_with_missing_definition_status(self) -> None:
        rows = thesis_rows(
            {
                "items": [
                    {
                        "symbol": "601899.SH",
                        "name": "紫金矿业",
                        "thesis": "待补充（用户未提供）",
                        "review_date": "2026-11-08",
                        "status": "needs_definition",
                        "status_reason": "缺少可验证的投资逻辑、验证指标和失效条件",
                    }
                ]
            }
        )

        self.assertEqual("待定义", rows[0]["状态"])
        self.assertEqual("2026-11-08", rows[0]["下次复核"])
        self.assertIn("缺少可验证", rows[0]["原因"])

    def test_formats_defined_thesis_rows_with_validation_and_invalidation(self) -> None:
        rows = thesis_rows(
            {
                "items": [
                    {
                        "symbol": "601899.SH",
                        "name": "紫金矿业",
                        "thesis": "铜金产量增长支持自由现金流改善",
                        "validation_metrics": "铜价与产量季度跟踪",
                        "invalid_conditions": "产量持续不及预期",
                        "review_date": "2026-11-08",
                        "status": "defined",
                        "status_reason": "已保存投资逻辑",
                    }
                ]
            }
        )

        self.assertEqual("铜价与产量季度跟踪", rows[0]["验证指标"])
        self.assertEqual("产量持续不及预期", rows[0]["失效条件"])

    def test_formats_decision_rows_with_import_status(self) -> None:
        rows = decision_rows(
            {
                "items": [
                    {
                        "legacy_key": "005",
                        "decision_date": "2025-09-20",
                        "symbol": "0700.HK",
                        "action": "建仓",
                        "thesis": "游戏收入未来 2 季度恢复增长",
                        "outcome_text": "收益 +32.5%",
                        "record_status": "complete",
                    },
                    {
                        "legacy_key": "007-600693.SH",
                        "decision_date": "2026-08-08",
                        "symbol": "600693.SH",
                        "action": "计划挂单卖出（限价单）",
                        "thesis": "题材股 + 零售复苏",
                        "outcome_text": None,
                        "record_status": "planned_record",
                    },
                ]
            }
        )

        self.assertEqual("完整", rows[0]["导入状态"])
        self.assertEqual("收益 +32.5%", rows[0]["结果"])
        self.assertEqual("计划记录（未确认执行）", rows[1]["导入状态"])
        self.assertEqual("600693.SH", rows[1]["股票"])

    def test_formats_normalized_financial_metric_rows_with_provenance(self) -> None:
        rows = financial_metric_rows(
            {
                "status": "available",
                "metrics": {
                    "total_revenue": {
                        "label": "营业总收入",
                        "value": 3_724_000_000.0,
                        "unit": "cny",
                        "report_date": "2026-03-31",
                        "source": "akshare.stock_financial_abstract_ths",
                        "fetched_at": "2026-08-09T10:00:00+00:00",
                    },
                    "gross_margin": {
                        "label": "销售毛利率",
                        "value": 17.07,
                        "unit": "percent",
                        "report_date": "2026-03-31",
                        "source": "akshare.stock_financial_abstract_ths",
                        "fetched_at": "2026-08-09T10:00:00+00:00",
                    },
                },
            }
        )

        self.assertEqual("37.24 亿", rows[0]["数值"])
        self.assertEqual("17.07%", rows[1]["数值"])
        self.assertEqual("2026-03-31", rows[0]["报告期"])
        self.assertEqual("akshare.stock_financial_abstract_ths", rows[0]["来源"])

    def test_formats_unavailable_financials_without_fabricated_rows(self) -> None:
        rows = financial_metric_rows({"status": "unavailable", "metrics": {}})

        self.assertEqual([], rows)

    def test_formats_recent_financial_history_as_read_only_rows(self) -> None:
        rows = financial_history_rows(
            {
                "history": [
                    {
                        "report_date": "2026-03-31",
                        "metrics": {
                            "total_revenue": {"value": 3_724_000_000.0, "unit": "cny"},
                            "net_profit": {"value": 242_000_000.0, "unit": "cny"},
                            "gross_margin": {"value": 17.07, "unit": "percent"},
                            "roe": {"value": 1.83, "unit": "percent"},
                            "debt_to_assets": {"value": 41.68, "unit": "percent"},
                        },
                    }
                ]
            }
        )

        self.assertEqual("2026-03-31", rows[0]["报告期"])
        self.assertEqual("37.24 亿", rows[0]["营业总收入"])
        self.assertEqual("2.42 亿", rows[0]["净利润"])
        self.assertEqual("17.07%", rows[0]["销售毛利率"])
        self.assertEqual("41.68%", rows[0]["资产负债率"])

    def test_formats_legacy_valuation_rows_with_provenance(self) -> None:
        rows = valuation_rows(
            {
                "status": "available",
                "metrics": {
                    "pe_ttm": {
                        "value": 53.64,
                        "source": "tencent",
                        "observed_at": "2026-08-08T14:25:15.077920",
                    },
                    "pb": {"value": 6.1, "source": "tencent", "observed_at": "2026-08-08T14:25:15.077920"},
                    "market_value_yi": {"value": 643.13, "source": "tencent", "observed_at": "2026-08-08T14:25:15.077920"},
                },
            }
        )

        self.assertEqual("PE TTM", rows[0]["指标"])
        self.assertEqual("53.64", rows[0]["数值"])
        self.assertEqual("tencent", rows[0]["来源"])
        self.assertEqual("643.13", rows[2]["数值"])


if __name__ == "__main__":
    unittest.main()
