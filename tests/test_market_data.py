import unittest

from backend.services.market_data import TencentMarketDataProvider


def tencent_line(symbol: str, name: str, price: str, change: str, change_pct: str) -> str:
    fields = ["" for _ in range(41)]
    fields[0] = "1"
    fields[1] = name
    fields[2] = symbol[-6:]
    fields[3] = price
    fields[4] = "34.90"
    fields[30] = "20260809103000"
    fields[31] = change
    fields[32] = change_pct
    return 'v_{symbol}="{fields}";'.format(symbol=symbol, fields="~".join(fields))


class TencentMarketDataProviderTests(unittest.TestCase):
    def test_parses_batch_quotes_with_source_and_observation_time(self) -> None:
        payload = "\n".join(
            [
                tencent_line("sh601899", "紫金矿业", "35.15", "0.25", "0.72"),
                tencent_line("sz001258", "立新能源", "13.16", "-0.12", "-0.90"),
            ]
        )
        provider = TencentMarketDataProvider(fetch_text=lambda _: payload)

        quotes = provider.get_quotes(["601899.SH", "001258.SZ"])

        self.assertEqual(35.15, quotes["601899.SH"].price)
        self.assertEqual("紫金矿业", quotes["601899.SH"].name)
        self.assertEqual("tencent_qt.gtimg.cn", quotes["601899.SH"].source)
        self.assertEqual("available", quotes["601899.SH"].status)
        self.assertEqual(-0.90, quotes["001258.SZ"].change_pct)
        self.assertEqual("20260809103000", quotes["001258.SZ"].observed_at)

    def test_marks_missing_symbols_unavailable_without_inventing_data(self) -> None:
        provider = TencentMarketDataProvider(fetch_text=lambda _: "")

        quotes = provider.get_quotes(["601899.SH"])

        self.assertIsNone(quotes["601899.SH"].price)
        self.assertEqual("unavailable", quotes["601899.SH"].status)
        self.assertEqual("tencent_qt.gtimg.cn", quotes["601899.SH"].source)

    def test_parses_tencent_simplified_index_fields(self) -> None:
        payload = 'v_s_sh000300="1~沪深300~000300~4694.44~43.13~0.93~239072020~78840576~~555008.96~ZS~";'
        provider = TencentMarketDataProvider(fetch_text=lambda _: payload)

        quote = provider.get_quotes(["sh000300"])["sh000300"]

        self.assertEqual(4694.44, quote.price)
        self.assertEqual(43.13, quote.change)
        self.assertEqual(0.93, quote.change_pct)
        self.assertAlmostEqual(4651.31, quote.previous_close)


if __name__ == "__main__":
    unittest.main()
