import re
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import pandas as pd


SOURCE = "akshare.stock_financial_abstract_ths"

COLUMN_DEFINITIONS = {
    "营业总收入": ("total_revenue", "money"),
    "营业总收入同比增长率": ("total_revenue_growth", "percent"),
    "净利润": ("net_profit", "money"),
    "净利润同比增长率": ("net_profit_growth", "percent"),
    "扣非净利润": ("deducted_net_profit", "money"),
    "扣非净利润同比增长率": ("deducted_net_profit_growth", "percent"),
    "基本每股收益": ("eps", "per_share"),
    "每股净资产": ("bps", "per_share"),
    "每股资本公积金": ("capital_reserve_per_share", "per_share"),
    "每股未分配利润": ("undistributed_profit_per_share", "per_share"),
    "每股经营现金流": ("operating_cash_flow_per_share", "per_share"),
    "销售净利率": ("net_margin", "percent"),
    "销售毛利率": ("gross_margin", "percent"),
    "净资产收益率": ("roe", "percent"),
    "净资产收益率-摊薄": ("roe_diluted", "percent"),
    "营业周期": ("operating_cycle_days", "days"),
    "存货周转率": ("inventory_turnover", "times"),
    "存货周转天数": ("inventory_turnover_days", "days"),
    "应收账款周转天数": ("receivable_turnover_days", "days"),
    "流动比率": ("current_ratio", "times"),
    "速动比率": ("quick_ratio", "times"),
    "保守速动比率": ("conservative_quick_ratio", "times"),
    "产权比率": ("debt_to_equity_ratio", "times"),
    "资产负债率": ("debt_to_assets", "percent"),
}

METRIC_LABELS = {
    canonical_key: column_name
    for column_name, (canonical_key, _) in COLUMN_DEFINITIONS.items()
}


class FinancialDataError(RuntimeError):
    """Raised when the upstream AkShare financial provider cannot return data."""


class FinancialDataProvider:
    def get_financial_abstract(self, symbol: str):
        """Return a pandas DataFrame of report-period financial indicators."""


class AkshareFinancialDataProvider:
    """Fetch the THS key financial indicators for one A-share symbol."""

    def __init__(
        self, fetch_abstract: Optional[Callable[[str], object]] = None
    ) -> None:
        self._fetch_abstract = fetch_abstract

    def get_financial_abstract(self, symbol: str):
        code = _extract_six_digit_code(symbol)
        try:
            if self._fetch_abstract is not None:
                frame = self._fetch_abstract(code)
            else:
                import akshare as ak

                frame = ak.stock_financial_abstract_ths(
                    symbol=code, indicator="按报告期"
                )
        except FinancialDataError:
            raise
        except Exception as error:
            raise FinancialDataError(
                "AkShare financial refresh failed: {}".format(error)
            ) from error
        if frame is None or len(frame) == 0:
            raise FinancialDataError("AkShare returned no financial report data.")
        return frame


def normalize_financial_frame(frame: pd.DataFrame) -> List[Dict[str, object]]:
    """Convert a THS indicator frame into canonical normalized metric records."""
    if frame is None or len(frame) == 0 or "报告期" not in frame.columns:
        return []
    records: List[Dict[str, object]] = []
    for _, row in frame.iterrows():
        report_date = _as_date_text(row.get("报告期"))
        if not report_date:
            continue
        for column_name, (metric_key, kind) in COLUMN_DEFINITIONS.items():
            if column_name not in frame.columns:
                continue
            value = _normalize_value(row.get(column_name), kind)
            records.append(
                {
                    "report_date": report_date,
                    "metric_key": metric_key,
                    "value": value,
                    "unit": _unit_for_kind(kind),
                }
            )
    return records


def refresh_stock_financials(
    connection: sqlite3.Connection,
    provider: FinancialDataProvider,
    symbol: str,
    fetched_at: Optional[str] = None,
) -> Dict[str, object]:
    """Refresh one stock's financial cache and return provenance and counts."""
    symbol = symbol.upper()
    stock = connection.execute(
        "SELECT id, symbol FROM stocks WHERE symbol = ?", (symbol,)
    ).fetchone()
    if stock is None:
        raise LookupError("Unknown stock symbol: " + symbol)

    frame = provider.get_financial_abstract(symbol)
    records = normalize_financial_frame(frame)
    if not records:
        raise FinancialDataError(
            "AkShare returned no normalized financial metrics for " + symbol
        )
    timestamp = fetched_at or datetime.now(timezone.utc).isoformat()

    with connection:
        for record in records:
            connection.execute(
                """
                INSERT INTO financial_metrics (
                    stock_id, report_date, metric_key, value, unit, source,
                    observed_at, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(stock_id, report_date, metric_key, source)
                DO UPDATE SET
                    value = excluded.value,
                    unit = excluded.unit,
                    observed_at = excluded.observed_at,
                    fetched_at = excluded.fetched_at
                """,
                (
                    stock["id"],
                    record["report_date"],
                    record["metric_key"],
                    record["value"],
                    record["unit"],
                    SOURCE,
                    timestamp,
                ),
            )

    report_dates = {record["report_date"] for record in records}
    return {
        "status": "refreshed",
        "symbol": symbol,
        "source": SOURCE,
        "fetched_at": timestamp,
        "report_periods": len(report_dates),
        "metrics": len(records),
    }


def load_latest_financial_metrics(
    connection: sqlite3.Connection, stock_id: int
) -> Dict[str, object]:
    """Load the normalized financial cache with latest values per metric."""
    rows = connection.execute(
        """
        SELECT report_date, metric_key, value, unit, source, observed_at, fetched_at
        FROM financial_metrics
        WHERE stock_id = ?
        ORDER BY report_date DESC, metric_key ASC
        """,
        (stock_id,),
    ).fetchall()
    latest: Dict[str, Dict[str, object]] = {}
    by_report_date: Dict[str, Dict[str, Dict[str, object]]] = {}
    for row in rows:
        metric_key = row["metric_key"]
        if metric_key not in latest:
            latest[metric_key] = {
                "key": metric_key,
                "label": METRIC_LABELS.get(metric_key, metric_key),
                "value": row["value"],
                "unit": row["unit"],
                "report_date": row["report_date"],
                "source": row["source"],
                "observed_at": row["observed_at"],
                "fetched_at": row["fetched_at"],
            }
        by_report_date.setdefault(row["report_date"], {})[metric_key] = {
            "value": row["value"],
            "unit": row["unit"],
        }
    history = [
        {"report_date": report_date, "metrics": metrics}
        for report_date, metrics in sorted(by_report_date.items(), reverse=True)
    ]
    return {
        "status": "available" if latest else "unavailable",
        "source": next((item["source"] for item in latest.values()), None),
        "latest_report_date": max(
            (item["report_date"] for item in latest.values()), default=None
        ),
        "metrics": latest,
        "history": history,
    }


def _extract_six_digit_code(symbol: str) -> str:
    match = re.search(r"\d{6}", symbol)
    if match is None:
        raise FinancialDataError("Invalid A-share symbol: " + symbol)
    return match.group(0)


def _as_date_text(value: object) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return str(value.isoformat())[:10]
        except (TypeError, ValueError):
            pass
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else None


def _normalize_value(value: object, kind: str) -> Optional[float]:
    if value is None or value is False:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text in ("", "False", "false", "None", "nan"):
        return None
    if kind == "money":
        return _parse_money(text)
    if kind == "percent":
        return _parse_number(text.rstrip("%"))
    return _parse_number(text)


def _parse_money(text: str) -> Optional[float]:
    match = re.search(r"(-?)([\d,]+(?:\.\d+)?)\s*(万亿|亿|万)?", text)
    if match is None:
        return _parse_number(text)
    number = float(match.group(2).replace(",", ""))
    if match.group(1) == "-":
        number = -number
    multiplier = {"万亿": 1e12, "亿": 1e8, "万": 1e4}.get(match.group(3) or "", 1)
    return number * multiplier


def _parse_number(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _unit_for_kind(kind: str) -> str:
    return {
        "money": "cny",
        "per_share": "cny",
        "percent": "percent",
        "times": "times",
        "days": "days",
    }.get(kind, "number")
