import json
import sqlite3
from typing import Callable, Dict, Optional


LEGACY_METRIC_EXTRACTORS: Dict[str, Callable[[Dict[str, object]], Optional[float]]] = {
    "pe_ttm": lambda payload: _as_float(payload.get("pe_ttm")),
    "pb": lambda payload: _as_float(payload.get("pb")),
    "market_value_yi": lambda payload: _as_float(payload.get("total_mv_yi")),
    "profit_growth": lambda payload: _as_float(
        _find_by_prefix(
            _as_dict(payload.get("data")),
            "归属母公司股东的净利润(同比增长率)",
        )
    ),
    "gross_margin": lambda payload: _as_float(
        _find_by_prefix(_as_dict(payload.get("data")), "销售毛利率")
    ),
}

NORMALIZED_TO_SCREEN = {
    "net_profit_growth": "profit_growth",
    "total_revenue_growth": "revenue_growth",
    "gross_margin": "gross_margin",
    "roe": "roe",
}


def load_screener_metrics(
    connection: sqlite3.Connection,
) -> Dict[str, Dict[str, object]]:
    """Load screening metrics from the normalized cache with legacy fallback."""
    stocks: Dict[str, Dict[str, object]] = {}
    normalized_rows = connection.execute(
        """
        SELECT stocks.symbol, stocks.name, stocks.sector, stocks.industry,
               financial_metrics.metric_key, financial_metrics.value,
               financial_metrics.source, financial_metrics.fetched_at
        FROM financial_metrics
        JOIN stocks ON stocks.id = financial_metrics.stock_id
        ORDER BY financial_metrics.report_date DESC, financial_metrics.metric_key ASC
        """
    ).fetchall()
    for row in normalized_rows:
        screen_key = NORMALIZED_TO_SCREEN.get(row["metric_key"])
        if screen_key is None or row["value"] is None:
            continue
        item = _ensure_item(stocks, row)
        if screen_key not in item["metrics"]:
            item["metrics"][screen_key] = row["value"]
            item["sources"][screen_key] = row["source"]
            item["observed_at"][screen_key] = row["fetched_at"]

    legacy_rows = connection.execute(
        """
        SELECT stocks.symbol, stocks.name, stocks.sector, stocks.industry,
               financial_snapshots.source, financial_snapshots.observed_at,
               financial_snapshots.data_json
        FROM financial_snapshots
        JOIN stocks ON stocks.id = financial_snapshots.stock_id
        ORDER BY financial_snapshots.observed_at ASC, financial_snapshots.id ASC
        """
    ).fetchall()
    for row in legacy_rows:
        item = _ensure_item(stocks, row)
        payload = json.loads(row["data_json"])
        for metric_key, value in extract_legacy_metrics(payload).items():
            if value is None or metric_key in item["metrics"]:
                continue
            item["metrics"][metric_key] = value
            item["sources"][metric_key] = row["source"]
            item["observed_at"][metric_key] = row["observed_at"]
    return stocks


def load_valuation_metrics(
    connection: sqlite3.Connection, stock_id: int
) -> Dict[str, object]:
    """Load valuation snapshots from legacy records, newest non-null value wins."""
    rows = connection.execute(
        """
        SELECT source, observed_at, data_json
        FROM financial_snapshots
        WHERE stock_id = ?
        ORDER BY observed_at ASC, id ASC
        """,
        (stock_id,),
    ).fetchall()
    metrics: Dict[str, Dict[str, object]] = {}
    for row in rows:
        payload = json.loads(row["data_json"])
        for metric_key, value in extract_legacy_metrics(payload).items():
            if metric_key not in ("pe_ttm", "pb", "market_value_yi") or value is None:
                continue
            metrics[metric_key] = {
                "value": value,
                "source": row["source"],
                "observed_at": row["observed_at"],
            }
    return {
        "status": "available" if metrics else "unavailable",
        "metrics": metrics,
        "reason": None
        if metrics
        else "本地暂无可验证的 PE、PB 或市值估值快照。",
    }


def extract_legacy_metrics(
    payload: Dict[str, object],
) -> Dict[str, Optional[float]]:
    """Extract the preserved legacy screening metrics without inventing values."""
    return {
        metric_key: extractor(payload)
        for metric_key, extractor in LEGACY_METRIC_EXTRACTORS.items()
    }


def _ensure_item(
    stocks: Dict[str, Dict[str, object]], row: sqlite3.Row
) -> Dict[str, object]:
    symbol = row["symbol"]
    return stocks.setdefault(
        symbol,
        {
            "symbol": symbol,
            "name": row["name"],
            "sector": row["sector"],
            "industry": row["industry"],
            "metrics": {},
            "sources": {},
            "observed_at": {},
        },
    )


def _as_dict(value: object) -> Dict[str, object]:
    return value if isinstance(value, dict) else {}


def _find_by_prefix(values: Dict[str, object], prefix: str) -> object:
    return next((value for key, value in values.items() if key.startswith(prefix)), None)


def _as_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
