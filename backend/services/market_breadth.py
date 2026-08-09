import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd


SOURCE = "akshare.stock_zh_a_spot_em"


class MarketBreadthError(RuntimeError):
    """Raised when the upstream breadth provider cannot return a snapshot."""


class MarketBreadthProvider:
    def get_breadth(self) -> Dict[str, object]:
        """Return a verified A-share market breadth snapshot."""


class AkshareMarketBreadthProvider:
    """Fetch the Eastmoney full A-share snapshot and compute breadth counts."""

    def __init__(
        self, fetch_frame: Optional[Callable[[], object]] = None
    ) -> None:
        self._fetch_frame = fetch_frame

    def get_breadth(self) -> Dict[str, object]:
        try:
            if self._fetch_frame is not None:
                frame = self._fetch_frame()
            else:
                import akshare as ak

                frame = ak.stock_zh_a_spot_em()
        except Exception as error:
            raise MarketBreadthError(
                "AkShare market breadth refresh failed: {}".format(error)
            ) from error
        if frame is None or len(frame) == 0:
            raise MarketBreadthError("AkShare returned an empty market snapshot.")
        return compute_market_breadth(frame)


class SinaMarketBreadthProvider:
    """Fallback breadth source using the Sina full A-share snapshot."""

    def __init__(
        self, fetch_frame: Optional[Callable[[], object]] = None
    ) -> None:
        self._fetch_frame = fetch_frame

    def get_breadth(self) -> Dict[str, object]:
        try:
            if self._fetch_frame is not None:
                frame = self._fetch_frame()
            else:
                import akshare as ak

                frame = ak.stock_zh_a_spot()
        except Exception as error:
            raise MarketBreadthError(
                "AkShare Sina market breadth refresh failed: {}".format(error)
            ) from error
        if frame is None or len(frame) == 0:
            raise MarketBreadthError("Sina returned an empty market snapshot.")
        return compute_market_breadth(frame)


class FallbackMarketBreadthProvider:
    """Try each breadth provider in order and retain the first verified result."""

    def __init__(self, *providers: MarketBreadthProvider) -> None:
        self._providers = providers

    def get_breadth(self) -> Dict[str, object]:
        errors = []
        for provider in self._providers:
            try:
                return provider.get_breadth()
            except MarketBreadthError as error:
                errors.append(str(error))
        raise MarketBreadthError("All market breadth providers failed: " + "; ".join(errors))


class CachedMarketBreadthProvider:
    """Serve fresh breadth from SQLite and fall back to the last successful snapshot."""

    CACHE_TABLE = "market_breadth_cache"

    def __init__(
        self,
        provider: MarketBreadthProvider,
        database_path: Path = Path("data/atlas.db"),
        ttl_seconds: float = 900.0,
    ) -> None:
        self._provider = provider
        self._database_path = Path(database_path)
        self._ttl_seconds = ttl_seconds

    def get_breadth(self) -> Dict[str, object]:
        cached = self._load_latest()
        if cached is not None and self._is_fresh(cached["cached_at"]):
            return self._cached_response(cached)
        try:
            breadth = self._provider.get_breadth()
        except MarketBreadthError as error:
            if cached is not None:
                result = self._cached_response(cached)
                result["reason"] = "使用最近成功快照；{}".format(error)
                return result
            raise
        self._save(breadth)
        return breadth

    def cache_info(self) -> Dict[str, object]:
        cached = self._load_latest()
        if cached is None:
            return {"breadth_cached": False}
        return {
            "breadth_cached": True,
            "breadth_age_seconds": max(
                0.0, time.time() - _timestamp(cached["cached_at"])
            ),
        }

    def _is_fresh(self, cached_at: str) -> bool:
        try:
            age_seconds = time.time() - _timestamp(cached_at)
        except (TypeError, ValueError):
            return False
        return 0 <= age_seconds < self._ttl_seconds

    def _load_latest(self) -> Optional[Dict[str, object]]:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT as_of, advancers, decliners, unchanged, limit_up,
                       limit_down, turnover_yi, source, cached_at, status
                FROM market_breadth_cache
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def _save(self, breadth: Dict[str, object]) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute("DELETE FROM market_breadth_cache")
                connection.execute(
                    """
                    INSERT INTO market_breadth_cache (
                        as_of, advancers, decliners, unchanged, limit_up,
                        limit_down, turnover_yi, source, cached_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        breadth.get("as_of"),
                        breadth.get("advancers"),
                        breadth.get("decliners"),
                        breadth.get("unchanged"),
                        breadth.get("limit_up"),
                        breadth.get("limit_down"),
                        breadth.get("turnover_yi"),
                        breadth.get("source"),
                        datetime.now(timezone.utc).isoformat(),
                        breadth.get("status"),
                    ),
                )
        finally:
            connection.close()

    def _cached_response(self, cached: Dict[str, object]) -> Dict[str, object]:
        return {
            "status": "available",
            "as_of": cached["as_of"],
            "advancers": cached["advancers"],
            "decliners": cached["decliners"],
            "unchanged": cached["unchanged"],
            "limit_up": cached["limit_up"],
            "limit_down": cached["limit_down"],
            "turnover_yi": cached["turnover_yi"],
            "source": cached["source"],
            "cached_at": cached["cached_at"],
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._database_path))
        connection.row_factory = sqlite3.Row
        return connection


def compute_market_breadth(frame: pd.DataFrame) -> Dict[str, object]:
    """Compute advancers, decliners, limit moves and turnover from a spot frame."""
    pct_change = pd.to_numeric(frame.get("涨跌幅"), errors="coerce")
    turnover = pd.to_numeric(frame.get("成交额"), errors="coerce").sum(min_count=1)
    codes = frame.get("代码", pd.Series(dtype=str)).astype(str).str[-6:]
    names = frame.get("名称", pd.Series(dtype=str)).astype(str)
    thresholds = pd.Series(9.8, index=frame.index)
    thresholds[codes.str.startswith(("300", "301", "688", "689"))] = 19.8
    thresholds[codes.str.startswith(("8", "4", "920"))] = 29.8
    thresholds[names.str.upper().str.contains("ST", na=False)] = 4.8

    return {
        "status": "available",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "advancers": int((pct_change > 0).sum()),
        "decliners": int((pct_change < 0).sum()),
        "unchanged": int((pct_change == 0).sum()),
        "limit_up": int(((pct_change >= thresholds) & (pct_change > 0)).sum()),
        "limit_down": int(((pct_change <= -thresholds) & (pct_change < 0)).sum()),
        "turnover_yi": round(float(turnover) / 1e8, 2) if turnover == turnover else None,
        "total": int(pct_change.notna().sum()),
        "source": SOURCE,
    }


def _timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()
