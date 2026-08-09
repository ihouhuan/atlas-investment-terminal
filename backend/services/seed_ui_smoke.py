import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from backend.database.connection import connect
from backend.database.schema import initialize_database


QUOTE_FIXTURES = {
    "sh000300": (4694.44, 0.93),
    "sz399006": (3563.12, 1.35),
    "sh000688": (1744.02, 2.51),
}


def seed_ui_smoke_cache(database_path: Path) -> None:
    """Seed deterministic market cache rows so UI smoke runs without live feeds."""
    connection = connect(database_path)
    try:
        initialize_database(connection)
        now = datetime.now(timezone.utc).isoformat()
        with connection:
            connection.execute("DELETE FROM market_breadth_cache")
            connection.execute(
                """
                INSERT INTO market_breadth_cache (
                    as_of, advancers, decliners, unchanged, limit_up,
                    limit_down, turnover_yi, source, cached_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    2830,
                    2140,
                    130,
                    42,
                    9,
                    12860.35,
                    "ui-smoke-fixture",
                    now,
                    "available",
                ),
            )
            for symbol, (price, change_pct) in QUOTE_FIXTURES.items():
                previous_close = round(price / (1 + change_pct / 100.0), 2)
                connection.execute(
                    """
                    INSERT INTO market_quote_cache (
                        symbol, name, price, previous_close, change,
                        change_pct, observed_at, fetched_at, source,
                        status, error, cached_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        name = excluded.name,
                        price = excluded.price,
                        previous_close = excluded.previous_close,
                        change = excluded.change,
                        change_pct = excluded.change_pct,
                        observed_at = excluded.observed_at,
                        fetched_at = excluded.fetched_at,
                        source = excluded.source,
                        status = excluded.status,
                        error = excluded.error,
                        cached_at = excluded.cached_at
                    """,
                    (
                        symbol,
                        "UI smoke fixture",
                        price,
                        previous_close,
                        round(price - previous_close, 2),
                        change_pct,
                        now,
                        now,
                        "ui-smoke-fixture",
                        "available",
                        now,
                    ),
                )
    finally:
        connection.close()


def main(arguments: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed deterministic market cache for UI smoke.")
    parser.add_argument("--database", type=Path, default=Path("data/atlas.db"))
    parsed_arguments = parser.parse_args(arguments)
    seed_ui_smoke_cache(parsed_arguments.database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
