import unittest

from backend.services.intelligence import build_morning_intelligence


def _portfolio(
    violation_count: int = 0,
    cash_ratio: float = 0.3,
    missing_thesis: int = 0,
) -> dict:
    violations = []
    if violation_count:
        violations.append(
            {
                "type": "position_limit",
                "symbol": "601899.SH",
                "name": "紫金矿业",
                "message": "持仓权重超过 core 仓位上限。",
            }
        )
    integrity_items = []
    if missing_thesis:
        integrity_items.append(
            {
                "type": "missing_thesis",
                "symbol": "000021.SZ",
                "name": "深科技",
                "message": "缺少手动定义的 Thesis。",
            }
        )
    return {
        "summary": {"cash_ratio": cash_ratio},
        "risk": {"violation_count": violation_count, "violations": violations},
        "research_integrity": {
            "missing_thesis_count": missing_thesis,
            "items": integrity_items,
        },
    }


class MorningIntelligenceTests(unittest.TestCase):
    def test_positive_market_state_uses_breadth_and_index_changes(self) -> None:
        market = {
            "indices": [{"name": "沪深300", "change_pct": 1.2}],
            "breadth": {
                "advancers": 3000,
                "decliners": 2000,
                "limit_up": 80,
                "limit_down": 5,
            },
        }

        intelligence = build_morning_intelligence(market, _portfolio(), {"items": []})

        self.assertEqual("偏积极", intelligence["market"]["label"])
        self.assertIn("上涨 3000 / 下跌 2000", intelligence["market"]["reasons"])

    def test_cautious_market_state_when_decliners_dominate(self) -> None:
        market = {
            "indices": [{"name": "沪深300", "change_pct": -1.5}],
            "breadth": {
                "advancers": 1500,
                "decliners": 3500,
                "limit_up": 12,
                "limit_down": 70,
            },
        }

        intelligence = build_morning_intelligence(market, _portfolio(), {"items": []})

        self.assertEqual("偏谨慎", intelligence["market"]["label"])

    def test_portfolio_state_marks_high_risk_with_violations_and_low_cash(self) -> None:
        intelligence = build_morning_intelligence(
            {"indices": [], "breadth": {}},
            _portfolio(violation_count=2, cash_ratio=0.05),
            {"items": []},
        )

        self.assertEqual("高风险", intelligence["portfolio"]["label"])

    def test_focus_includes_violations_thesis_and_open_actions(self) -> None:
        intelligence = build_morning_intelligence(
            {"indices": [], "breadth": {}},
            _portfolio(violation_count=1, missing_thesis=1),
            {
                "items": [
                    {
                        "action_text": "复核新能源仓位",
                        "decision_legacy_key": "007",
                    }
                ]
            },
        )

        kinds = [item["kind"] for item in intelligence["focus"]]
        self.assertIn("风险违规", kinds)
        self.assertIn("缺 Thesis", kinds)
        self.assertIn("行动项", kinds)

    def test_empty_focus_when_nothing_needs_attention(self) -> None:
        intelligence = build_morning_intelligence(
            {"indices": [], "breadth": {}},
            _portfolio(),
            {"items": []},
        )

        self.assertEqual([], intelligence["focus"])


if __name__ == "__main__":
    unittest.main()
