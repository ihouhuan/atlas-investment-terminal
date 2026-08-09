import argparse
import json
from pathlib import Path
from typing import Dict, Sequence

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.legacy_import import import_legacy_atlas, import_legacy_financial_snapshots, import_legacy_watchlist
from backend.services.risk_budget import install_canonical_risk_budget


def initialize_atlas_database(database_path: Path, legacy_root: Path) -> Dict[str, int]:
    """Create an Atlas database and import its first verified legacy snapshot."""
    connection = connect(database_path)
    try:
        initialize_database(connection)
        portfolio_path = legacy_root / "portfolio" / "portfolio.json"
        portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
        source_as_of = str(portfolio.get("last_updated") or "") or None
        with connection:
            install_canonical_risk_budget(
                connection,
                str(legacy_root / "portfolio" / "仓位预算.md"),
                source_as_of or "unknown",
                manage_transaction=False,
            )
            results = import_legacy_atlas(
                connection, legacy_root, manage_transaction=False
            )
            results["watchlist_items"] = import_legacy_watchlist(
                connection,
                legacy_root / "china_market" / "data" / "user_watchlist.json",
                manage_transaction=False,
            )
            results["financial_snapshots"] = import_legacy_financial_snapshots(
                connection,
                legacy_root / "china_market" / "data" / "stock_fundamentals.jsonl",
                manage_transaction=False,
            )
        results["risk_budget_versions"] = 1
        return results
    finally:
        connection.close()


def main(arguments: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize the Atlas 2.0 local database.")
    parser.add_argument("--database", type=Path, default=Path("data/atlas.db"))
    parser.add_argument(
        "--legacy-root", type=Path, default=Path("legacy/openclaw-atlas")
    )
    parsed_arguments = parser.parse_args(arguments)
    results = initialize_atlas_database(
        parsed_arguments.database, parsed_arguments.legacy_root
    )
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
