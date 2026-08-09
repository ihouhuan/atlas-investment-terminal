import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional


def build_decision_journal(connection: sqlite3.Connection) -> Dict[str, object]:
    """Return migrated decision records with explicit import-completeness status."""
    rows = connection.execute(
        """
        SELECT decisions.id AS decision_id, legacy_key, decision_date, symbol, action, price_text, position_text,
               investment_reason, thesis, validation_metrics, maximum_risk,
               invalid_conditions, expected_horizon, outcome_text, source_path,
               decision_updates.id AS update_id, decision_updates.event_type,
               decision_updates.execution_date, decision_updates.execution_price,
               decision_updates.actual_result, decision_updates.review_notes,
               decision_updates.source_note AS update_source_note,
               decision_updates.created_at AS update_created_at
        FROM decisions
        LEFT JOIN decision_updates ON decision_updates.id = (
            SELECT id FROM decision_updates
            WHERE decision_updates.decision_id = decisions.id
            ORDER BY decision_updates.created_at DESC, decision_updates.id DESC
            LIMIT 1
        )
        ORDER BY decision_date IS NULL, decision_date DESC, decisions.id DESC
        """
    ).fetchall()
    items = [_decision_item(row) for row in rows]
    return {
        "items": items,
        "total": len(items),
        "incomplete_import_count": sum(item["record_status"] == "incomplete_import" for item in items),
        "planned_record_count": sum(item["record_status"] == "planned_record" for item in items),
    }


def _decision_item(row: sqlite3.Row) -> Dict[str, object]:
    incomplete = not row["decision_date"] or not row["symbol"] or not row["action"]
    planned = not incomplete and row["action"].startswith("计划")
    item = {
        "legacy_key": row["legacy_key"],
        "decision_date": row["decision_date"],
        "symbol": row["symbol"],
        "action": row["action"],
        "price_text": row["price_text"],
        "position_text": row["position_text"],
        "investment_reason": row["investment_reason"],
        "thesis": row["thesis"],
        "validation_metrics": row["validation_metrics"],
        "maximum_risk": row["maximum_risk"],
        "invalid_conditions": row["invalid_conditions"],
        "expected_horizon": row["expected_horizon"],
        "outcome_text": row["outcome_text"],
        "source_path": row["source_path"],
        "record_status": "incomplete_import" if incomplete else "planned_record" if planned else "complete",
        "record_status_reason": "旧 Markdown 的双标的表格无法自动拆分，日期或代码未迁移。"
        if incomplete
        else "从旧日志的双标的表格拆分的计划记录，未确认成交或执行。"
        if planned
        else "字段已从旧决策日志迁移；内容仍应结合原始记录复核。",
    }
    item["latest_update"] = _update_item(row) if row["update_id"] is not None else None
    return item


def create_decision_update(
    connection: sqlite3.Connection,
    legacy_key: str,
    event_type: str,
    execution_date: Optional[str],
    execution_price: Optional[str],
    actual_result: Optional[str],
    review_notes: Optional[str],
    source_note: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, object]:
    """Append a user-authored execution or review event to one historic decision."""
    if event_type not in {"not_executed", "executed", "reviewed"}:
        raise ValueError("Unsupported decision event type: " + event_type)
    if not _has_text(actual_result) and not _has_text(review_notes):
        raise ValueError("A decision update requires actual_result or review_notes.")
    decision = connection.execute(
        "SELECT id, legacy_key FROM decisions WHERE legacy_key = ?", (legacy_key,)
    ).fetchone()
    if decision is None:
        raise ValueError("Unknown decision key: " + legacy_key)
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO decision_updates (
                decision_id, event_type, execution_date, execution_price,
                actual_result, review_notes, source_note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision["id"], event_type, _clean_optional(execution_date), _clean_optional(execution_price),
                _clean_optional(actual_result), _clean_optional(review_notes), _clean_optional(source_note), timestamp,
            ),
        )
    return {"id": cursor.lastrowid, "legacy_key": decision["legacy_key"], "event_type": event_type, "created_at": timestamp}


def get_decision_updates(connection: sqlite3.Connection, legacy_key: str) -> Dict[str, object]:
    """Read an append-only event history for a decision record."""
    decision = connection.execute(
        "SELECT id, legacy_key FROM decisions WHERE legacy_key = ?", (legacy_key,)
    ).fetchone()
    if decision is None:
        raise ValueError("Unknown decision key: " + legacy_key)
    rows = connection.execute(
        """
        SELECT id, event_type, execution_date, execution_price, actual_result,
               review_notes, source_note, created_at
        FROM decision_updates
        WHERE decision_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (decision["id"],),
    ).fetchall()
    return {"legacy_key": decision["legacy_key"], "items": [dict(row) for row in rows], "total": len(rows)}


def _update_item(row: sqlite3.Row) -> Dict[str, object]:
    return {
        "id": row["update_id"], "event_type": row["event_type"],
        "execution_date": row["execution_date"], "execution_price": row["execution_price"],
        "actual_result": row["actual_result"], "review_notes": row["review_notes"],
        "source_note": row["update_source_note"], "created_at": row["update_created_at"],
    }


def _clean_optional(value: Optional[str]) -> Optional[str]:
    return value.strip() if value and value.strip() else None


def _has_text(value: Optional[str]) -> bool:
    return bool(_clean_optional(value))
