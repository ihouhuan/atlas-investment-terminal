import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.market_data import (
    MarketQuote,
    PersistentMarketDataProvider,
    TencentMarketDataProvider,
)


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


class StubLiveQuoteProvider:
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
                source="stub_live",
                status="available",
            )
            for symbol in symbols
        }


class StubUnavailableQuoteProvider:
    def get_quotes(self, symbols):
        return {
            symbol: MarketQuote(
                symbol=symbol,
                name=None,
                price=None,
                previous_close=None,
                change=None,
                change_pct=None,
                observed_at=None,
                fetched_at="2026-08-09T10:31:00+00:00",
                source="stub_offline",
                status="unavailable",
                error="offline",
            )
            for symbol in symbols
        }


class FailingQuoteProvider:
    def get_quotes(self, symbols):
        raise ConnectionError("offline")


class PersistentMarketDataProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "atlas.db"
        connection = connect(self.database_path)
        initialize_database(connection)
        connection.close()
        self.addCleanup(self.temporary_directory.cleanup)

    def test_saves_live_quotes_and_falls_back_after_restart(self) -> None:
        persistent = PersistentMarketDataProvider(
            StubLiveQuoteProvider(), self.database_path
        )
        first = persistent.get_quotes(["000021.SZ"])
        self.assertEqual("available", first["000021.SZ"].status)

        restarted = PersistentMarketDataProvider(
            StubUnavailableQuoteProvider(), self.database_path
        )
        second = restarted.get_quotes(["000021.SZ"])

        self.assertEqual("available", second["000021.SZ"].status)
        self.assertEqual("stub_live", second["000021.SZ"].source)
        self.assertIsNotNone(second["000021.SZ"].cached_at)

    def test_falls_back_when_live_provider_raises(self) -> None:
        PersistentMarketDataProvider(
            StubLiveQuoteProvider(), self.database_path
        ).get_quotes(["000021.SZ"])

        persistent = PersistentMarketDataProvider(
            FailingQuoteProvider(), self.database_path
        )
        quote = persistent.get_quotes(["000021.SZ"])["000021.SZ"]

        self.assertEqual("available", quote.status)
        self.assertIsNotNone(quote.cached_at)

    def test_reports_persisted_cache_info(self) -> None:
        persistent = PersistentMarketDataProvider(
            StubLiveQuoteProvider(), self.database_path
        )
        persistent.get_quotes(["000021.SZ", "601899.SH"])

        info = persistent.cache_info()

        self.assertTrue(info["persisted"])
        self.assertEqual(2, info["persisted_symbols"])


if __name__ == "__main__":
    unittest.main()
