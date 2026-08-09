from datetime import date, datetime, timezone
import sqlite3
from typing import Dict, Optional


def save_brief_snapshot(
    connection: sqlite3.Connection,
    portfolio: Dict[str, object],
    created_at: Optional[str] = None,
    research_conclusion: Optional[str] = None,
) -> Dict[str, object]:
    """Persist a user-requested, local-only morning-brief baseline."""
    integrity = portfolio["research_integrity"]
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    conclusion = research_conclusion.strip() if research_conclusion else None
    with connection:
        cursor = connection.execute(
            "INSERT INTO morning_brief_snapshots (created_at, risk_violation_count, missing_thesis_count, unconfirmed_plan_count, source_path, research_conclusion) VALUES (?, ?, ?, ?, ?, ?)",
            (
                timestamp,
                portfolio["risk"]["violation_count"],
                integrity["missing_thesis_count"],
                integrity["unconfirmed_plan_count"],
                portfolio["summary"]["source_path"],
                conclusion,
            ),
        )
    return {"id": cursor.lastrowid, "created_at": timestamp, "research_conclusion": conclusion}


SNAPSHOT_COLUMNS = (
    "id, created_at, risk_violation_count, missing_thesis_count, "
    "unconfirmed_plan_count, source_path, research_conclusion, review_status, reviewed_at, review_notes"
)


def list_brief_snapshots(connection: sqlite3.Connection, limit: int = 100) -> Dict[str, object]:
    """List locally saved morning-brief snapshots without changing them."""
    rows = connection.execute(
        "SELECT {} FROM morning_brief_snapshots ORDER BY id DESC LIMIT ?".format(SNAPSHOT_COLUMNS),
        (limit,),
    ).fetchall()
    return {"total": len(rows), "items": [dict(row) for row in rows]}


def _get_snapshot(connection: sqlite3.Connection, snapshot_id: int) -> Optional[Dict[str, object]]:
    row = connection.execute(
        "SELECT {} FROM morning_brief_snapshots WHERE id = ?".format(SNAPSHOT_COLUMNS),
        (snapshot_id,),
    ).fetchone()
    return dict(row) if row else None


def update_brief_review_status(
    connection: sqlite3.Connection,
    snapshot_id: int,
    reviewed: bool,
    reviewed_at: Optional[str] = None,
    review_notes: Optional[str] = None,
) -> Dict[str, object]:
    """Record an explicit local review decision for a saved morning brief."""
    snapshot = _get_snapshot(connection, snapshot_id)
    if snapshot is None:
        raise ValueError("未找到晨报快照。")
    status = "reviewed" if reviewed else "unreviewed"
    timestamp = (reviewed_at or snapshot["reviewed_at"] or datetime.now(timezone.utc).date().isoformat()) if reviewed else None
    notes = review_notes.strip() if review_notes else None
    with connection:
        connection.execute(
            "UPDATE morning_brief_snapshots SET review_status = ?, reviewed_at = ?, review_notes = ? WHERE id = ?",
            (status, timestamp, notes, snapshot_id),
        )
    return _get_snapshot(connection, snapshot_id)


def create_follow_up_action(
    connection: sqlite3.Connection,
    snapshot_id: int,
    action_text: str,
    decision_legacy_key: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: str = "normal",
) -> Dict[str, object]:
    """Create a user-authored, incomplete follow-up for a reviewed morning brief."""
    snapshot = _get_snapshot(connection, snapshot_id)
    if snapshot is None:
        raise ValueError("未找到晨报快照。")
    if snapshot["review_status"] != "reviewed":
        raise ValueError("请先将晨报标记为已复盘，再添加行动项。")
    text = action_text.strip()
    if not text:
        raise ValueError("行动项不能为空。")
    if priority not in {"high", "normal", "low"}:
        raise ValueError("不支持的行动项优先级。")
    decision_key = decision_legacy_key.strip() if decision_legacy_key else None
    if decision_key and connection.execute("SELECT 1 FROM decisions WHERE legacy_key = ?", (decision_key,)).fetchone() is None:
        raise ValueError("未找到关联的决策日志记录。")
    timestamp = datetime.now(timezone.utc).isoformat()
    with connection:
        cursor = connection.execute(
            "INSERT INTO morning_brief_follow_up_actions (snapshot_id, action_text, decision_legacy_key, due_date, priority, status, created_at) VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (snapshot_id, text, decision_key, due_date.strip() if due_date else None, priority, timestamp),
        )
    return {"id": cursor.lastrowid, "snapshot_id": snapshot_id, "action_text": text, "decision_legacy_key": decision_key, "due_date": due_date.strip() if due_date else None, "priority": priority, "status": "open", "created_at": timestamp, "completed_at": None}


def list_follow_up_actions(connection: sqlite3.Connection, snapshot_id: int) -> Dict[str, object]:
    """List action items for a single local morning-brief review."""
    if _get_snapshot(connection, snapshot_id) is None:
        raise ValueError("未找到晨报快照。")
    rows = connection.execute(
        "SELECT id, snapshot_id, action_text, decision_legacy_key, due_date, priority, status, created_at, completed_at FROM morning_brief_follow_up_actions WHERE snapshot_id = ? ORDER BY status, due_date IS NULL, due_date, id DESC",
        (snapshot_id,),
    ).fetchall()
    return {"snapshot_id": snapshot_id, "items": [_action_item(row) for row in rows], "total": len(rows)}


def list_all_follow_up_actions(
    connection: sqlite3.Connection, status: str = "open", due_window: str = "all"
) -> Dict[str, object]:
    """Aggregate local review actions with their morning-brief context."""
    if status not in {"open", "completed"}:
        raise ValueError("不支持的行动项状态。")
    if due_window not in {"all", "today", "week"}:
        raise ValueError("不支持的截止日期筛选。")
    rows = connection.execute(
        """
        SELECT actions.id, actions.snapshot_id, actions.action_text, actions.decision_legacy_key,
               actions.due_date, actions.priority, actions.status, actions.created_at, actions.completed_at,
               snapshots.created_at AS snapshot_created_at, snapshots.reviewed_at
        FROM morning_brief_follow_up_actions AS actions
        JOIN morning_brief_snapshots AS snapshots ON snapshots.id = actions.snapshot_id
        WHERE actions.status = ?
        ORDER BY CASE WHEN actions.due_date IS NOT NULL AND actions.due_date < date('now') THEN 0 ELSE 1 END,
                 CASE actions.priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                 actions.due_date IS NULL, actions.due_date, actions.created_at ASC, actions.id ASC
        """,
        (status,),
    ).fetchall()
    items = [_action_item(row) for row in rows]
    today = date.today()
    week_end = today.fromordinal(today.toordinal() + (6 - today.weekday()))
    if due_window == "today":
        items = [item for item in items if item["due_date"] == today.isoformat()]
    elif due_window == "week":
        items = [item for item in items if item["due_date"] and today.isoformat() <= item["due_date"] <= week_end.isoformat()]
    summary = connection.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed FROM morning_brief_follow_up_actions"
    ).fetchone()
    total_actions = summary["total"]
    completed_actions = summary["completed"] or 0
    return {
        "status": status,
        "due_window": due_window,
        "items": items,
        "total": len(items),
        "summary": {
            "total": total_actions,
            "completed": completed_actions,
            "open": total_actions - completed_actions,
            "completion_rate": round(completed_actions / total_actions * 100, 1) if total_actions else 0.0,
        },
    }


def follow_up_action_trend(connection: sqlite3.Connection, days: int) -> Dict[str, object]:
    """Summarize recent action creation and completion without changing records."""
    if days not in {7, 30}:
        raise ValueError("趋势周期仅支持 7 或 30 天。")
    rows = connection.execute(
        """
        SELECT date(created_at) AS action_date, COUNT(*) AS created,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM morning_brief_follow_up_actions
        WHERE date(created_at) >= date('now', ?)
        GROUP BY date(created_at)
        ORDER BY action_date
        """,
        ("-{} days".format(days - 1),),
    ).fetchall()
    items = [dict(row) for row in rows]
    created = sum(item["created"] for item in items)
    completed = sum(item["completed"] or 0 for item in items)
    return {
        "days": days,
        "items": items,
        "summary": {
            "created": created,
            "completed": completed,
            "completion_rate": round(completed / created * 100, 1) if created else 0.0,
        },
    }


def alert_acknowledgement(connection: sqlite3.Connection, alert_key: str) -> Dict[str, object]:
    row = connection.execute("SELECT acknowledged_at FROM alert_acknowledgements WHERE alert_key = ?", (alert_key,)).fetchone()
    return {"alert_key": alert_key, "acknowledged": row is not None, "acknowledged_at": row["acknowledged_at"] if row else None}


def acknowledge_alert(connection: sqlite3.Connection, alert_key: str) -> Dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with connection:
        connection.execute("INSERT OR REPLACE INTO alert_acknowledgements (alert_key, acknowledged_at) VALUES (?, ?)", (alert_key, timestamp))
    return {"alert_key": alert_key, "acknowledged": True, "acknowledged_at": timestamp}


def update_follow_up_action(
    connection: sqlite3.Connection, snapshot_id: int, action_id: int, completed: bool
) -> Dict[str, object]:
    """Mark one review action completed or reopen it without changing its text."""
    row = connection.execute(
        "SELECT id FROM morning_brief_follow_up_actions WHERE id = ? AND snapshot_id = ?",
        (action_id, snapshot_id),
    ).fetchone()
    if row is None:
        raise ValueError("未找到晨报行动项。")
    status = "completed" if completed else "open"
    completed_at = datetime.now(timezone.utc).isoformat() if completed else None
    with connection:
        connection.execute(
            "UPDATE morning_brief_follow_up_actions SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, action_id),
        )
    return dict(
        connection.execute(
            "SELECT id, snapshot_id, action_text, decision_legacy_key, due_date, priority, status, created_at, completed_at FROM morning_brief_follow_up_actions WHERE id = ?",
            (action_id,),
        ).fetchone()
    )


def _action_item(row: sqlite3.Row) -> Dict[str, object]:
    item = dict(row)
    item["is_overdue"] = bool(item["status"] == "open" and item["due_date"] and item["due_date"] < date.today().isoformat())
    return item


def latest_brief_delta(
    connection: sqlite3.Connection,
    current_id: Optional[int] = None,
    previous_id: Optional[int] = None,
) -> Dict[str, object]:
    """Compare either the latest pair or two user-selected local snapshots."""
    if current_id is not None:
        current = _get_snapshot(connection, current_id)
        if current is None:
            raise ValueError("未找到当前晨报快照。")
    else:
        current_row = connection.execute(
            "SELECT {} FROM morning_brief_snapshots ORDER BY id DESC LIMIT 1".format(SNAPSHOT_COLUMNS)
        ).fetchone()
        current = dict(current_row) if current_row else None

    if current is None:
        return {"status": "unavailable", "reason": "尚无已保存晨报。"}

    if previous_id is not None:
        previous = _get_snapshot(connection, previous_id)
        if previous is None:
            raise ValueError("未找到对比晨报快照。")
        if previous["id"] == current["id"]:
            raise ValueError("请选择两份不同的晨报快照进行比较。")
    else:
        previous_row = connection.execute(
            "SELECT {} FROM morning_brief_snapshots WHERE id < ? ORDER BY id DESC LIMIT 1".format(SNAPSHOT_COLUMNS),
            (current["id"],),
        ).fetchone()
        previous = dict(previous_row) if previous_row else None

    if previous is None:
        return {
            "status": "baseline",
            "current": current,
            "reason": "已保存首份晨报，下一次保存后可比较变化。",
        }
    keys = ("risk_violation_count", "missing_thesis_count", "unconfirmed_plan_count")
    return {
        "status": "available",
        "current": current,
        "previous": previous,
        "changes": {key: current[key] - previous[key] for key in keys},
    }
