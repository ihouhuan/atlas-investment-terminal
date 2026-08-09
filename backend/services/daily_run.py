import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Sequence

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.brief_report import morning_brief_markdown
from backend.services.financial_refresh import (
    AkshareFinancialDataProvider,
    FinancialDataProvider,
    refresh_stock_financials_batch,
)
from backend.services.market_breadth import (
    AkshareMarketBreadthProvider,
    FallbackMarketBreadthProvider,
    MarketBreadthProvider,
    SinaMarketBreadthProvider,
)
from backend.services.market_data import (
    AkshareMarketDataProvider,
    CachedMarketDataProvider,
    FallbackMarketDataProvider,
    MarketDataProvider,
    PersistentMarketDataProvider,
    TencentMarketDataProvider,
)
from backend.services.market_overview import build_market_overview
from backend.services.morning_brief import latest_brief_delta, save_brief_snapshot
from backend.services.portfolio_analysis import build_portfolio_overview
from backend.services.screener import screen_stocks


def run_daily(
    connection: sqlite3.Connection,
    market_provider: MarketDataProvider,
    breadth_provider: MarketBreadthProvider,
    financial_provider: Optional[FinancialDataProvider] = None,
    output_dir: Path = Path("reports/daily"),
    financial_scope: str = "none",
    run_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    """Run one reproducible local daily research pipeline and return a manifest."""
    run_at = now or datetime.now(timezone.utc)
    run_at_text = run_at.isoformat()
    run_id = run_id or run_at.strftime("%Y%m%d-%H%M%S")
    market = build_market_overview(market_provider, breadth_provider)
    if hasattr(market_provider, "cache_info"):
        market["cache"] = market_provider.cache_info()
    portfolio = build_portfolio_overview(connection)
    screener = screen_stocks(connection)

    financial_summary = None
    if financial_scope != "none" and financial_provider is not None:
        symbols = _scope_symbols(connection, financial_scope)
        financial_summary = refresh_stock_financials_batch(
            connection, financial_provider, symbols
        )

    delta = latest_brief_delta(connection)
    snapshot = save_brief_snapshot(connection, portfolio)
    markdown = morning_brief_markdown(market, portfolio, screener, delta)
    report_dir = output_dir / run_at.date().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "atlas-morning-brief-{}.md".format(run_id)
    report_path.write_text(markdown, encoding="utf-8")

    available_indices = sum(
        1 for item in market.get("indices", []) if item.get("status") == "available"
    )
    return {
        "status": "completed" if available_indices else "degraded",
        "run_id": run_id,
        "run_at": run_at_text,
        "market": {
            "indices": len(market.get("indices", [])),
            "available": available_indices,
            "breadth_status": market.get("breadth", {}).get("status"),
        },
        "financial_refresh": financial_summary,
        "morning_brief_snapshot_id": snapshot["id"],
        "report_path": str(report_path),
        "source_path": portfolio["summary"]["source_path"],
    }


def main(
    arguments: Optional[Sequence[str]] = None,
    market_provider: Optional[MarketDataProvider] = None,
    breadth_provider: Optional[MarketBreadthProvider] = None,
    financial_provider: Optional[FinancialDataProvider] = None,
) -> int:
    parser = argparse.ArgumentParser(description="Run the Atlas local daily research pipeline.")
    parser.add_argument("--database", type=Path, default=Path("data/atlas.db"))
    parser.add_argument(
        "--financial-scope",
        choices=("none", "watchlist", "all", "portfolio"),
        default="none",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports/daily"))
    parser.add_argument("--run-id")
    parsed = parser.parse_args(arguments)

    connection = connect(parsed.database)
    try:
        initialize_database(connection)
        if market_provider is None:
            market_provider = PersistentMarketDataProvider(
                CachedMarketDataProvider(
                    FallbackMarketDataProvider(
                        TencentMarketDataProvider(),
                        AkshareMarketDataProvider(),
                    )
                ),
                database_path=parsed.database,
            )
        if breadth_provider is None:
            breadth_provider = FallbackMarketBreadthProvider(
                AkshareMarketBreadthProvider(),
                SinaMarketBreadthProvider(),
            )
        if financial_provider is None:
            financial_provider = AkshareFinancialDataProvider()
        result = run_daily(
            connection,
            market_provider,
            breadth_provider,
            financial_provider,
            parsed.output_dir,
            parsed.financial_scope,
            parsed.run_id,
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
