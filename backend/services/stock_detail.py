import json
import sqlite3
from dataclasses import asdict
from typing import Dict

from backend.services.financial_refresh import load_latest_financial_metrics
from backend.services.financial_metrics import load_valuation_metrics
from backend.services.market_data import MarketDataProvider


def build_stock_detail(connection: sqlite3.Connection, provider: MarketDataProvider, symbol: str) -> Dict[str, object]:
    """Return a company record with separate current quote and historical snapshots."""
    stock = connection.execute(
        "SELECT id, symbol, name, exchange, sector, industry FROM stocks WHERE symbol = ?", (symbol.upper(),)
    ).fetchone()
    if stock is None:
        raise LookupError("Unknown stock symbol: " + symbol)
    snapshots = connection.execute(
        """
        SELECT source, observed_at, data_json, source_path
        FROM financial_snapshots WHERE stock_id = ? ORDER BY id DESC
        """,
        (stock["id"],),
    ).fetchall()
    quote = provider.get_quotes([stock["symbol"]])[stock["symbol"]]
    financial_history = _latest_history(snapshots)
    flow_data = financial_history["data"]
    financials = load_latest_financial_metrics(connection, stock["id"])
    valuation = load_valuation_metrics(connection, stock["id"])
    if financials["status"] == "unavailable":
        financials["reason"] = "本地尚无 AkShare 财务缓存；可通过刷新财务数据获取。"
    return {
        "company": {"symbol": stock["symbol"], "name": stock["name"], "exchange": stock["exchange"], "sector": stock["sector"], "industry": stock["industry"]},
        "quote": asdict(quote),
        "financial_history": financial_history,
        "fund_flow": {
            "status": financial_history["status"],
            "main_inflow": flow_data.get("main_inflow"),
            "fund_in": flow_data.get("fund_in"),
            "fund_out": flow_data.get("fund_out"),
            "source": financial_history.get("source"),
            "observed_at": financial_history.get("observed_at"),
        },
        "valuation": valuation,
        "financials": financials,
    }


def _latest_history(snapshots) -> Dict[str, object]:
    if not snapshots:
        return {"status": "unavailable", "source_path": None, "observed_at": None, "data": {}}
    snapshot = snapshots[0]
    return {
        "status": "historical_snapshot",
        "source": snapshot["source"],
        "source_path": snapshot["source_path"],
        "observed_at": snapshot["observed_at"],
        "data": json.loads(snapshot["data_json"]),
    }
