import sqlite3
from dataclasses import asdict
from typing import Dict, List

from backend.services.market_data import MarketDataProvider


def get_watchlist(
    connection: sqlite3.Connection, provider: MarketDataProvider, limit: int
) -> Dict[str, object]:
    """Read the persisted stock pool and attach current quote status per stock."""
    total = connection.execute("SELECT COUNT(*) FROM watchlist_items").fetchone()[0]
    records = connection.execute(
        """
        SELECT stocks.symbol, stocks.name, stocks.exchange, stocks.sector, stocks.industry,
               watchlist_items.category, watchlist_items.source_path
        FROM watchlist_items
        JOIN stocks ON stocks.id = watchlist_items.stock_id
        ORDER BY stocks.symbol
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    quotes = provider.get_quotes([record["symbol"] for record in records])
    items: List[Dict[str, object]] = []
    for record in records:
        items.append(
            {
                "symbol": record["symbol"],
                "name": record["name"],
                "exchange": record["exchange"],
                "sector": record["sector"],
                "industry": record["industry"],
                "category": record["category"],
                "source_path": record["source_path"],
                "quote": asdict(quotes[record["symbol"]]),
            }
        )
    return {"total": total, "items": items}
