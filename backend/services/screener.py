import json
import sqlite3
from typing import Dict, List, Optional


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
    metrics_by_symbol = _load_metrics(connection)
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
        "available_metrics": ["pe_ttm", "pb", "profit_growth", "gross_margin", "market_value_yi"],
        "unavailable_metrics": ["roe", "revenue_growth"],
        "items": items[:limit],
        "total": len(items),
    }


def _load_metrics(connection: sqlite3.Connection) -> Dict[str, Dict[str, object]]:
    records = connection.execute(
        """
        SELECT stocks.symbol, stocks.name, stocks.sector, stocks.industry,
               financial_snapshots.source, financial_snapshots.observed_at,
               financial_snapshots.source_path, financial_snapshots.data_json
        FROM financial_snapshots
        JOIN stocks ON stocks.id = financial_snapshots.stock_id
        ORDER BY financial_snapshots.observed_at ASC, financial_snapshots.id ASC
        """
    ).fetchall()
    stocks: Dict[str, Dict[str, object]] = {}
    for record in records:
        symbol = record["symbol"]
        item = stocks.setdefault(
            symbol,
            {
                "symbol": symbol,
                "name": record["name"],
                "sector": record["sector"],
                "industry": record["industry"],
                "metrics": {},
                "sources": {},
                "observed_at": {},
            },
        )
        payload = json.loads(record["data_json"])
        for metric, value in _metrics_from_payload(payload).items():
            if value is None:
                continue
            item["metrics"][metric] = value
            item["sources"][metric] = record["source"]
            item["observed_at"][metric] = record["observed_at"]
    return stocks


def _metrics_from_payload(payload: Dict[str, object]) -> Dict[str, Optional[float]]:
    fundamentals = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "pe_ttm": _as_float(payload.get("pe_ttm")),
        "pb": _as_float(payload.get("pb")),
        "market_value_yi": _as_float(payload.get("total_mv_yi")),
        "profit_growth": _as_float(_find_by_prefix(fundamentals, "归属母公司股东的净利润(同比增长率)")),
        "gross_margin": _as_float(_find_by_prefix(fundamentals, "销售毛利率")),
    }


def _find_by_prefix(values: Dict[str, object], prefix: str) -> object:
    return next((value for key, value in values.items() if key.startswith(prefix)), None)


def _as_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _within_maximum(value: Optional[float], maximum: Optional[float]) -> bool:
    return maximum is None or (value is not None and 0 < value <= maximum)


def _within_minimum(value: Optional[float], minimum: Optional[float]) -> bool:
    return minimum is None or (value is not None and value >= minimum)
