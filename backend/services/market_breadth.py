from datetime import datetime, timezone
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
