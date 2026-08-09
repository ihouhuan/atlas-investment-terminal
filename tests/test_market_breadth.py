import unittest

import pandas as pd

from backend.services.market_breadth import (
    AkshareMarketBreadthProvider,
    FallbackMarketBreadthProvider,
    MarketBreadthError,
    SinaMarketBreadthProvider,
    compute_market_breadth,
)


def sample_spot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["000001", "300001", "600519", "600001", "688001", "920001", "000002"],
            "名称": ["平安银行", "宁德时代", "贵州茅台", "ST测试", "科创板", "北交所", "万科A"],
            "最新价": [10.0, 100.0, 1500.0, 5.0, 20.0, 10.0, 8.0],
            "涨跌幅": [1.2, 20.5, 9.9, 5.1, -20.2, 30.0, -2.0],
            "成交额": [1e9, 2e9, 3e9, 0.5e9, 1e9, 0.2e9, 1e9],
        }
    )


def sina_spot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["sz000001", "sh600519", "bj920001", "sz300001"],
            "名称": ["平安银行", "贵州茅台", "北交所", "宁德时代"],
            "最新价": [10.0, 1500.0, 10.0, 100.0],
            "涨跌幅": [1.2, 9.9, 30.0, 20.5],
            "成交额": [1e9, 3e9, 0.2e9, 2e9],
        }
    )


class MarketBreadthTests(unittest.TestCase):
    def test_computes_advancers_decliners_limit_moves_and_turnover(self) -> None:
        breadth = compute_market_breadth(sample_spot_frame())

        self.assertEqual("available", breadth["status"])
        self.assertEqual(5, breadth["advancers"])
        self.assertEqual(2, breadth["decliners"])
        self.assertEqual(4, breadth["limit_up"])
        self.assertEqual(1, breadth["limit_down"])
        self.assertEqual(87.0, breadth["turnover_yi"])
        self.assertEqual("akshare.stock_zh_a_spot_em", breadth["source"])

    def test_provider_uses_injected_frame(self) -> None:
        provider = AkshareMarketBreadthProvider(fetch_frame=sample_spot_frame)

        breadth = provider.get_breadth()

        self.assertEqual("available", breadth["status"])
        self.assertEqual(4, breadth["limit_up"])

    def test_provider_rejects_empty_frame(self) -> None:
        provider = AkshareMarketBreadthProvider(
            fetch_frame=lambda: pd.DataFrame()
        )

        with self.assertRaises(MarketBreadthError):
            provider.get_breadth()

    def test_sina_provider_handles_prefixed_codes(self) -> None:
        provider = SinaMarketBreadthProvider(fetch_frame=sina_spot_frame)

        breadth = provider.get_breadth()

        self.assertEqual("available", breadth["status"])
        self.assertEqual(4, breadth["advancers"])
        self.assertEqual(3, breadth["limit_up"])
        self.assertEqual(62.0, breadth["turnover_yi"])

    def test_fallback_uses_second_provider_when_first_fails(self) -> None:
        class FailingBreadthProvider:
            def get_breadth(self):
                raise MarketBreadthError("eastmoney offline")

        provider = FallbackMarketBreadthProvider(
            FailingBreadthProvider(),
            SinaMarketBreadthProvider(fetch_frame=sina_spot_frame),
        )

        breadth = provider.get_breadth()

        self.assertEqual("available", breadth["status"])
        self.assertEqual(62.0, breadth["turnover_yi"])


if __name__ == "__main__":
    unittest.main()
