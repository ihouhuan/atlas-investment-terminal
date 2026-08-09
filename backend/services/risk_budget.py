import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict


CANONICAL_RISK_BUDGET: Dict[str, Any] = {
    "name": "A股三层仓位预算",
    "tiers": {
        "core": {"single_stock_max": 0.15, "sector_max": 0.40},
        "growth": {"single_stock_max": 0.08, "sector_max": 0.30},
        "thematic": {"single_stock_max": 0.03, "total_max": 0.10},
    },
    "portfolio": {
        "minimum_cash": 0.20,
        "maximum_leverage": 0.0,
        "daily_loss_review_trigger": -0.03,
    },
    "status": "active",
}

CANONICAL_RISK_BUDGET_VERSION = "china-equity-tiered-v1.1"


def install_canonical_risk_budget(
    connection: sqlite3.Connection,
    source_path: str,
    source_as_of: str,
) -> int:
    """Install the sole active risk-budget version without duplicating it."""
    with connection:
        existing = connection.execute(
            "SELECT id FROM risk_budget_versions WHERE version = ?",
            (CANONICAL_RISK_BUDGET_VERSION,),
        ).fetchone()
        connection.execute("UPDATE risk_budget_versions SET is_active = 0")

        if existing is not None:
            connection.execute(
                "UPDATE risk_budget_versions SET is_active = 1 WHERE id = ?",
                (existing["id"],),
            )
            return int(existing["id"])

        cursor = connection.execute(
            """
            INSERT INTO risk_budget_versions (
                version, rules_json, source_path, source_as_of, is_active, created_at
            ) VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                CANONICAL_RISK_BUDGET_VERSION,
                json.dumps(CANONICAL_RISK_BUDGET, ensure_ascii=False, sort_keys=True),
                source_path,
                source_as_of,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return int(cursor.lastrowid)


def get_active_risk_budget(connection: sqlite3.Connection) -> Dict[str, Any]:
    """Return the active risk budget or fail when no active version exists."""
    row = connection.execute(
        "SELECT rules_json FROM risk_budget_versions WHERE is_active = 1"
    ).fetchone()
    if row is None:
        raise LookupError("No active Atlas risk budget is installed.")
    return json.loads(row["rules_json"])
