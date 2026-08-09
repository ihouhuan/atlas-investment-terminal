import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional


PLACEHOLDER_PREFIX = "待补充"


def build_thesis_overview(connection: sqlite3.Connection) -> Dict[str, object]:
    """Present persisted thesis records without treating placeholders as validated ideas."""
    snapshot = connection.execute(
        """
        SELECT id, as_of_date, source_path
        FROM portfolio_snapshots
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if snapshot is None:
        return {"as_of_date": None, "source_path": None, "items": [], "total": 0, "needs_definition_count": 0}

    rows = connection.execute(
        """
        SELECT stocks.symbol, stocks.name, portfolio_positions.thesis AS legacy_thesis,
               portfolio_positions.review_date AS legacy_review_date,
               thesis_versions.id AS version_id, thesis_versions.thesis AS version_thesis,
               thesis_versions.validation_metrics, thesis_versions.invalid_conditions,
               thesis_versions.review_date AS version_review_date, thesis_versions.entry_source,
               thesis_versions.source_note, thesis_versions.created_at
        FROM portfolio_positions
        JOIN stocks ON stocks.id = portfolio_positions.stock_id
        LEFT JOIN thesis_versions ON thesis_versions.id = (
            SELECT id FROM thesis_versions
            WHERE thesis_versions.stock_id = stocks.id
            ORDER BY thesis_versions.created_at DESC, thesis_versions.id DESC
            LIMIT 1
        )
        WHERE portfolio_positions.snapshot_id = ?
        ORDER BY stocks.symbol
        """,
        (snapshot["id"],),
    ).fetchall()
    items = [_thesis_item(row, snapshot["source_path"]) for row in rows]
    return {
        "as_of_date": snapshot["as_of_date"],
        "source_path": snapshot["source_path"],
        "items": items,
        "total": len(items),
        "needs_definition_count": sum(item["status"] == "needs_definition" for item in items),
    }


def _thesis_item(row: sqlite3.Row, source_path: str) -> Dict[str, object]:
    manual_entry = row["version_id"] is not None
    thesis = row["version_thesis"] if manual_entry else row["legacy_thesis"] or ""
    needs_definition = not thesis.strip() or thesis.startswith(PLACEHOLDER_PREFIX)
    return {
        "symbol": row["symbol"],
        "name": row["name"],
        "thesis": thesis or "未提供",
        "validation_metrics": row["validation_metrics"] if manual_entry else None,
        "invalid_conditions": row["invalid_conditions"] if manual_entry else None,
        "review_date": row["version_review_date"] if manual_entry else row["legacy_review_date"],
        "status": "needs_definition" if needs_definition else "defined",
        "status_reason": "缺少可验证的投资逻辑、验证指标和失效条件"
        if needs_definition
        else "已保存投资逻辑；仍需人工核验验证指标与失效条件。",
        "source_path": source_path,
        "entry_source": row["entry_source"] if manual_entry else "legacy_portfolio_snapshot",
        "entry_source_note": row["source_note"] if manual_entry else None,
        "entry_created_at": row["created_at"] if manual_entry else None,
    }


def create_thesis_version(
    connection: sqlite3.Connection,
    symbol: str,
    thesis: str,
    validation_metrics: str,
    invalid_conditions: str,
    review_date: str,
    source_note: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, object]:
    """Append a user-authored thesis version without modifying older versions."""
    values = {
        "thesis": thesis,
        "validation_metrics": validation_metrics,
        "invalid_conditions": invalid_conditions,
        "review_date": review_date,
    }
    empty_fields = [name for name, value in values.items() if not value or not value.strip()]
    if empty_fields:
        raise ValueError("Missing required thesis fields: " + ", ".join(empty_fields))
    stock = connection.execute(
        "SELECT id, symbol FROM stocks WHERE symbol = ?", (symbol.upper(),)
    ).fetchone()
    if stock is None:
        raise ValueError("Unknown stock symbol: " + symbol.upper())
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO thesis_versions (
                stock_id, thesis, validation_metrics, invalid_conditions, review_date,
                entry_source, source_note, created_at
            ) VALUES (?, ?, ?, ?, ?, 'user_entry', ?, ?)
            """,
            (
                stock["id"],
                thesis.strip(),
                validation_metrics.strip(),
                invalid_conditions.strip(),
                review_date.strip(),
                source_note.strip() if source_note and source_note.strip() else None,
                timestamp,
            ),
        )
    return {"id": cursor.lastrowid, "symbol": stock["symbol"], "created_at": timestamp, "entry_source": "user_entry"}


def get_thesis_versions(connection: sqlite3.Connection, symbol: str) -> Dict[str, object]:
    """Return append-only user-authored thesis versions for one known stock."""
    stock = connection.execute(
        "SELECT id, symbol FROM stocks WHERE symbol = ?", (symbol.upper(),)
    ).fetchone()
    if stock is None:
        raise ValueError("Unknown stock symbol: " + symbol.upper())
    rows = connection.execute(
        """
        SELECT id, thesis, validation_metrics, invalid_conditions, review_date,
               entry_source, source_note, created_at
        FROM thesis_versions
        WHERE stock_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (stock["id"],),
    ).fetchall()
    return {
        "symbol": stock["symbol"],
        "items": [dict(row) for row in rows],
        "total": len(rows),
    }
