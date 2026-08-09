import sqlite3
from typing import Dict, List, Optional

from backend.services.financial_metrics import load_screener_metrics


def screen_stocks(
    connection: sqlite3.Connection,
    max_pe_ttm: Optional[float] = None,
    max_pb: Optional[float] = None,
    min_profit_growth: Optional[float] = None,
    min_gross_margin: Optional[float] = None,
    sector: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, object]:
    """Screen only preserved historical metrics and retain their provenance."""
    metrics_by_symbol = load_screener_metrics(connection)
    items = []
    for item in metrics_by_symbol.values():
        metrics = item["metrics"]
        if sector and item["sector"] != sector:
            continue
        if not _within_maximum(metrics.get("pe_ttm"), max_pe_ttm):
            continue
        if not _within_maximum(metrics.get("pb"), max_pb):
            continue
        if not _within_minimum(metrics.get("profit_growth"), min_profit_growth):
            continue
        if not _within_minimum(metrics.get("gross_margin"), min_gross_margin):
            continue
        items.append(item)

    items.sort(key=lambda item: item["symbol"])
    return {
        "data_status": "historical_snapshot",
        "filters": {
            "max_pe_ttm": max_pe_ttm,
            "max_pb": max_pb,
            "min_profit_growth": min_profit_growth,
            "min_gross_margin": min_gross_margin,
            "sector": sector,
        },
        "available_metrics": [
            "pe_ttm",
            "pb",
            "profit_growth",
            "gross_margin",
            "market_value_yi",
            "roe",
            "revenue_growth",
        ],
        "unavailable_metrics": [],
        "items": items[:limit],
        "total": len(items),
    }


def _within_maximum(value: Optional[float], maximum: Optional[float]) -> bool:
    return maximum is None or (value is not None and 0 < value <= maximum)


def _within_minimum(value: Optional[float], minimum: Optional[float]) -> bool:
    return minimum is None or (value is not None and value >= minimum)
