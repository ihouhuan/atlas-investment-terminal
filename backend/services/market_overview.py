from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List

from backend.services.market_data import MarketDataProvider


MARKET_INDICES = (
    ("沪深300", "sh000300"),
    ("创业板指", "sz399006"),
    ("科创50", "sh000688"),
)


def build_market_overview(provider: MarketDataProvider) -> Dict[str, object]:
    """Build an A-share market overview without estimating unsupported breadth data."""
    symbols = [symbol for _, symbol in MARKET_INDICES]
    quotes = provider.get_quotes(symbols)
    indices: List[Dict[str, object]] = []
    for name, symbol in MARKET_INDICES:
        item = asdict(quotes[symbol])
        item["name"] = name
        indices.append(item)
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "indices": indices,
        "breadth": {
            "advancers": None,
            "decliners": None,
            "limit_up": None,
            "limit_down": None,
            "turnover": None,
            "status": "unavailable",
            "source": None,
            "reason": "Current configured sources do not provide verified market breadth.",
        },
    }
