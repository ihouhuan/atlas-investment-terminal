import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional, Sequence

from backend.database.connection import connect
from backend.services.financial_refresh import (
    AkshareFinancialDataProvider,
    FinancialDataProvider,
    refresh_stock_financials_batch,
)


def main(arguments: Optional[Sequence[str]] = None, provider: Optional[FinancialDataProvider] = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh Atlas financial caches in bulk.")
    parser.add_argument("--database", type=Path, default=Path("data/atlas.db"))
    parser.add_argument(
        "--scope",
        choices=("all", "watchlist", "portfolio"),
        default="all",
        help="Which stock universe to refresh.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of stocks.")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbol list.")
    parsed = parser.parse_args(arguments)

    if parsed.symbols:
        symbols = [
            symbol.strip().upper()
            for symbol in parsed.symbols.split(",")
            if symbol.strip()
        ]
    else:
        connection = connect(parsed.database)
        try:
            symbols = _scope_symbols(connection, parsed.scope)
        finally:
            connection.close()
        if parsed.limit is not None:
            symbols = symbols[: parsed.limit]

    connection = connect(parsed.database)
    try:
        result = refresh_stock_financials_batch(
            connection,
            provider or AkshareFinancialDataProvider(),
            symbols,
        )
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _scope_symbols(connection: sqlite3.Connection, scope: str) -> list:
    if scope == "watchlist":
        query = """
        SELECT DISTINCT stocks.symbol
        FROM watchlist_items
        JOIN stocks ON stocks.id = watchlist_items.stock_id
        ORDER BY stocks.symbol
        """
    elif scope == "portfolio":
        query = """
        SELECT DISTINCT stocks.symbol
        FROM portfolio_positions
        JOIN stocks ON stocks.id = portfolio_positions.stock_id
        ORDER BY stocks.symbol
        """
    else:
        query = "SELECT symbol FROM stocks ORDER BY symbol"
    return [row["symbol"] for row in connection.execute(query).fetchall()]


if __name__ == "__main__":
    raise SystemExit(main())
