from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from time import monotonic
from typing import Callable, Dict, Iterable, Optional, Protocol
from urllib.request import Request, urlopen


TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q={symbols}"
REQUEST_HEADERS = {
    "User-Agent": "Atlas-Investment-Terminal/2.0",
    "Referer": "https://stockapp.finance.qq.com/",
}


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    name: Optional[str]
    price: Optional[float]
    previous_close: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]
    observed_at: Optional[str]
    fetched_at: str
    source: str
    status: str
    error: Optional[str] = None
    cached_at: Optional[str] = None


class MarketDataProvider(Protocol):
    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, MarketQuote]:
        """Return one quote result per requested symbol."""


class CachedMarketDataProvider:
    """Keep a short-lived in-memory quote cache for interactive dashboard refreshes."""

    def __init__(self, provider: MarketDataProvider, ttl_seconds: float = 45.0) -> None:
        self._provider = provider
        self._ttl_seconds = ttl_seconds
        self._cached_at = 0.0
        self._quotes: Dict[str, MarketQuote] = {}

    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, MarketQuote]:
        requested_symbols = list(symbols)
        if monotonic() - self._cached_at >= self._ttl_seconds or any(symbol not in self._quotes for symbol in requested_symbols):
            self._quotes = self._provider.get_quotes(requested_symbols)
            self._cached_at = monotonic()
        return {symbol: self._quotes[symbol] for symbol in requested_symbols}

    def clear_cache(self) -> None:
        """Invalidate cached quotes for an explicit user refresh."""
        self._cached_at = 0.0
        self._quotes = {}

    def cache_info(self) -> Dict[str, object]:
        age_seconds = max(0.0, monotonic() - self._cached_at) if self._cached_at else None
        return {"ttl_seconds": self._ttl_seconds, "age_seconds": age_seconds, "cached": age_seconds is not None and age_seconds < self._ttl_seconds}


class PersistentMarketDataProvider:
    """Fall back to the latest successful SQLite quote snapshot when live data fails."""

    CACHE_TABLE = "market_quote_cache"

    def __init__(
        self,
        provider: MarketDataProvider,
        database_path: Path = Path("data/atlas.db"),
    ) -> None:
        self._provider = provider
        self._database_path = Path(database_path)

    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, MarketQuote]:
        requested_symbols = list(symbols)
        if not requested_symbols:
            return {}
        try:
            live_quotes = self._provider.get_quotes(requested_symbols)
        except Exception as error:
            live_quotes = {
                symbol: self._unavailable_quote(symbol, str(error))
                for symbol in requested_symbols
            }
        self._save_available_quotes(live_quotes)

        results: Dict[str, MarketQuote] = {}
        for symbol in requested_symbols:
            quote = live_quotes.get(symbol)
            if quote is not None and quote.status == "available":
                results[symbol] = quote
                continue
            cached = self._load_quote(symbol)
            if cached is not None:
                results[symbol] = cached
            else:
                results[symbol] = quote or self._unavailable_quote(
                    symbol, "No live or cached quote is available."
                )
        return results

    def clear_cache(self) -> None:
        """Invalidate only the in-memory cache; persisted snapshots remain for fallback."""
        clear = getattr(self._provider, "clear_cache", None)
        if callable(clear):
            clear()

    def cache_info(self) -> Dict[str, object]:
        info: Dict[str, object] = {}
        provider_cache_info = getattr(self._provider, "cache_info", None)
        if callable(provider_cache_info):
            info.update(provider_cache_info())
        info["persisted"] = True
        info["persisted_symbols"] = self._count_cached_symbols()
        return info

    def _save_available_quotes(self, quotes: Dict[str, MarketQuote]) -> None:
        available = [quote for quote in quotes.values() if quote.status == "available"]
        if not available:
            return
        connection = self._connect()
        try:
            with connection:
                for quote in available:
                    connection.execute(
                        """
                        INSERT INTO market_quote_cache (
                            symbol, name, price, previous_close, change, change_pct,
                            observed_at, fetched_at, source, status, error, cached_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', NULL, ?)
                        ON CONFLICT(symbol) DO UPDATE SET
                            name = excluded.name,
                            price = excluded.price,
                            previous_close = excluded.previous_close,
                            change = excluded.change,
                            change_pct = excluded.change_pct,
                            observed_at = excluded.observed_at,
                            fetched_at = excluded.fetched_at,
                            source = excluded.source,
                            status = excluded.status,
                            error = excluded.error,
                            cached_at = excluded.cached_at
                        """,
                        (
                            quote.symbol,
                            quote.name,
                            quote.price,
                            quote.previous_close,
                            quote.change,
                            quote.change_pct,
                            quote.observed_at,
                            quote.fetched_at,
                            quote.source,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
        finally:
            connection.close()

    def _load_quote(self, symbol: str) -> Optional[MarketQuote]:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT symbol, name, price, previous_close, change, change_pct,
                       observed_at, fetched_at, source, cached_at
                FROM market_quote_cache
                WHERE symbol = ?
                """,
                (symbol,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return MarketQuote(
            symbol=row["symbol"],
            name=row["name"],
            price=row["price"],
            previous_close=row["previous_close"],
            change=row["change"],
            change_pct=row["change_pct"],
            observed_at=row["observed_at"],
            fetched_at=row["fetched_at"],
            source=row["source"],
            status="available",
            error=None,
            cached_at=row["cached_at"],
        )

    def _count_cached_symbols(self) -> int:
        connection = self._connect()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM market_quote_cache").fetchone()[0])
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._database_path))
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _unavailable_quote(symbol: str, error: str) -> MarketQuote:
        return MarketQuote(
            symbol=symbol,
            name=None,
            price=None,
            previous_close=None,
            change=None,
            change_pct=None,
            observed_at=None,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source="none",
            status="unavailable",
            error=error,
        )


class TencentMarketDataProvider:
    """Fetch A-share and index quotes from Tencent's public quote endpoint."""

    def __init__(self, fetch_text: Optional[Callable[[str], str]] = None) -> None:
        self._fetch_text = fetch_text or self._request_text

    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, MarketQuote]:
        requested_symbols = list(symbols)
        if not requested_symbols:
            return {}
        token_to_symbol = {
            self._to_tencent_symbol(symbol): symbol for symbol in requested_symbols
        }
        url = TENCENT_QUOTE_URL.format(symbols=",".join(token_to_symbol))
        try:
            payload = self._fetch_text(url)
        except Exception as error:
            return {
                symbol: self._unavailable_quote(symbol, str(error))
                for symbol in requested_symbols
            }
        return self._parse_payload(payload, token_to_symbol)

    def _parse_payload(
        self, payload: str, token_to_symbol: Dict[str, str]
    ) -> Dict[str, MarketQuote]:
        parsed_quotes: Dict[str, MarketQuote] = {}
        fetched_at = datetime.now(timezone.utc).isoformat()
        for line in payload.splitlines():
            if "=" not in line:
                continue
            variable, raw_value = line.split("=", 1)
            token = variable.strip().removeprefix("v_")
            symbol = token_to_symbol.get(token)
            if symbol is None:
                continue
            content = raw_value.strip().strip(";").strip('"')
            fields = content.split("~")
            price = self._to_float(fields, 3)
            if token.startswith("s_"):
                change = self._to_float(fields, 4)
                change_pct = self._to_float(fields, 5)
                previous_close = price - change if price is not None and change is not None else None
                observed_at = None
            else:
                change = self._to_float(fields, 31)
                change_pct = self._to_float(fields, 32)
                previous_close = self._to_float(fields, 4)
                observed_at = self._to_text(fields, 30)
            parsed_quotes[symbol] = MarketQuote(
                symbol=symbol,
                name=self._to_text(fields, 1),
                price=price,
                previous_close=previous_close,
                change=change,
                change_pct=change_pct,
                observed_at=observed_at,
                fetched_at=fetched_at,
                source="tencent_qt.gtimg.cn",
                status="available" if price is not None else "unavailable",
                error=None if price is not None else "Tencent quote did not include a price.",
            )
        for symbol in token_to_symbol.values():
            if symbol not in parsed_quotes:
                parsed_quotes[symbol] = self._unavailable_quote(symbol, None, fetched_at)
        return parsed_quotes

    @staticmethod
    def _to_tencent_symbol(symbol: str) -> str:
        normalized = symbol.strip().lower()
        if normalized.startswith("s_sh") or normalized.startswith("s_sz"):
            return normalized
        if normalized.startswith(("sh", "sz", "bj")):
            if normalized[2:] in {"000300", "399006", "000688"}:
                return "s_" + normalized
            return normalized
        if normalized.endswith(".sh"):
            return "sh" + normalized[:-3]
        if normalized.endswith(".sz"):
            return "sz" + normalized[:-3]
        if normalized.endswith(".bj"):
            return "bj" + normalized[:-3]
        if len(normalized) == 6 and normalized.isdigit():
            return ("sh" if normalized.startswith(("6", "9")) else "sz") + normalized
        raise ValueError("Unsupported A-share symbol: " + symbol)

    @staticmethod
    def _to_float(fields: list, index: int) -> Optional[float]:
        try:
            return float(fields[index]) if fields[index] else None
        except (IndexError, ValueError):
            return None

    @staticmethod
    def _to_text(fields: list, index: int) -> Optional[str]:
        try:
            return fields[index] or None
        except IndexError:
            return None

    @staticmethod
    def _request_text(url: str) -> str:
        request = Request(url, headers=REQUEST_HEADERS)
        with urlopen(request, timeout=10) as response:
            return response.read().decode("gbk", errors="replace")

    @staticmethod
    def _unavailable_quote(
        symbol: str, error: Optional[str], fetched_at: Optional[str] = None
    ) -> MarketQuote:
        return MarketQuote(
            symbol=symbol,
            name=None,
            price=None,
            previous_close=None,
            change=None,
            change_pct=None,
            observed_at=None,
            fetched_at=fetched_at or datetime.now(timezone.utc).isoformat(),
            source="tencent_qt.gtimg.cn",
            status="unavailable",
            error=error or "Tencent quote is unavailable.",
        )


class AkshareMarketDataProvider:
    """Optional AkShare provider that is intentionally inactive when unavailable."""

    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, MarketQuote]:
        requested_symbols = list(symbols)
        try:
            import akshare as ak

            frame = ak.stock_zh_index_spot_em()
        except Exception as error:
            return {
                symbol: self._unavailable_quote(symbol, str(error))
                for symbol in requested_symbols
            }

        quotes: Dict[str, MarketQuote] = {}
        fetched_at = datetime.now(timezone.utc).isoformat()
        for symbol in requested_symbols:
            code = symbol[-6:]
            match = frame[frame["代码"].astype(str) == code]
            if match.empty:
                quotes[symbol] = self._unavailable_quote(symbol, "Index was not returned.", fetched_at)
                continue
            row = match.iloc[0]
            quotes[symbol] = MarketQuote(
                symbol=symbol,
                name=str(row.get("名称") or "") or None,
                price=_as_optional_float(row.get("最新价")),
                previous_close=None,
                change=_as_optional_float(row.get("涨跌额")),
                change_pct=_as_optional_float(row.get("涨跌幅")),
                observed_at=None,
                fetched_at=fetched_at,
                source="akshare.stock_zh_index_spot_em",
                status="available" if _as_optional_float(row.get("最新价")) is not None else "unavailable",
                error=None,
            )
        return quotes

    @staticmethod
    def _unavailable_quote(symbol: str, error: str, fetched_at: Optional[str] = None) -> MarketQuote:
        return MarketQuote(
            symbol=symbol,
            name=None,
            price=None,
            previous_close=None,
            change=None,
            change_pct=None,
            observed_at=None,
            fetched_at=fetched_at or datetime.now(timezone.utc).isoformat(),
            source="akshare.stock_zh_index_spot_em",
            status="unavailable",
            error=error,
        )


class FallbackMarketDataProvider:
    """Use each provider in order and retain the first real quote per symbol."""

    def __init__(self, *providers: MarketDataProvider) -> None:
        self._providers = providers

    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, MarketQuote]:
        requested_symbols = list(symbols)
        results: Dict[str, MarketQuote] = {}
        remaining_symbols = requested_symbols
        for provider in self._providers:
            if not remaining_symbols:
                break
            provider_quotes = provider.get_quotes(remaining_symbols)
            for symbol, quote in provider_quotes.items():
                if quote.status == "available":
                    results[symbol] = quote
            remaining_symbols = [
                symbol for symbol in requested_symbols if symbol not in results
            ]
        for symbol in remaining_symbols:
            results[symbol] = MarketQuote(
                symbol=symbol,
                name=None,
                price=None,
                previous_close=None,
                change=None,
                change_pct=None,
                observed_at=None,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                source="none",
                status="unavailable",
                error="No configured data provider returned a quote.",
            )
        return {symbol: results[symbol] for symbol in requested_symbols}


def _as_optional_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
