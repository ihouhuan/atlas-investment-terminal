import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


DECISION_HEADING = re.compile(r"^#{2,3} 决策 #(?P<number>\d+).*?$", re.MULTILINE)
TABLE_FIELD = re.compile(r"^\|\s*\*\*(?P<field>[^*]+)\*\*\s*\|\s*(?P<value>.*?)\s*\|$", re.MULTILINE)
TWO_SYMBOL_TABLE_FIELD = re.compile(
    r"^\|\s*\*\*(?P<field>[^*]+)\*\*\s*\|\s*(?P<first>.*?)\s*\|\s*(?P<second>.*?)\s*\|$",
    re.MULTILINE,
)
PROFILE_FIELD = re.compile(r"^\|\s*\*\*(?P<field>[^*]+)\*\*\s*\|\s*(?P<value>.*?)\s*\|$", re.MULTILINE)


def import_legacy_atlas(
    connection: sqlite3.Connection,
    legacy_root: Path,
    imported_at: Optional[datetime] = None,
    manage_transaction: bool = True,
) -> Dict[str, int]:
    """Import a single legacy Atlas snapshot while preserving source provenance."""
    if manage_transaction:
        with connection:
            return _import_legacy_atlas_inner(connection, legacy_root, imported_at)
    return _import_legacy_atlas_inner(connection, legacy_root, imported_at)


def _import_legacy_atlas_inner(
    connection: sqlite3.Connection,
    legacy_root: Path,
    imported_at: Optional[datetime] = None,
) -> Dict[str, int]:
    legacy_root = legacy_root.resolve()
    portfolio_path = legacy_root / "portfolio" / "portfolio.json"
    profile_path = legacy_root / "投资者档案" / "投资者档案.md"
    decisions_path = legacy_root / "决策日志" / "决策日志.md"
    import_key = "legacy-atlas:" + str(legacy_root)
    imported_timestamp = (imported_at or datetime.now(timezone.utc)).isoformat()

    _require_files(portfolio_path, profile_path, decisions_path)
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    source_as_of = str(portfolio.get("last_updated") or "") or None

    existing_run = connection.execute(
        "SELECT id FROM import_runs WHERE source_path = ?", (import_key,)
    ).fetchone()
    if existing_run is not None:
        decisions_text = decisions_path.read_text(encoding="utf-8")
        _repair_legacy_decision_007(
            connection, decisions_text, str(decisions_path), source_as_of, imported_timestamp
        )
        return {"positions": 0, "investor_profiles": 0, "decisions": 0}

    profile_text = profile_path.read_text(encoding="utf-8")
    decisions_text = decisions_path.read_text(encoding="utf-8")

    connection.execute(
        """
        INSERT INTO import_runs (source_path, source_as_of, imported_at, status, details)
        VALUES (?, ?, ?, 'completed', '')
        """,
        (import_key, source_as_of, imported_timestamp),
    )
    _import_investor_profile(
        connection, profile_text, str(profile_path), source_as_of, imported_timestamp
    )
    position_count = _import_portfolio(
        connection, portfolio, str(portfolio_path), source_as_of, imported_timestamp
    )
    decision_count = _import_decisions(
        connection, decisions_text, str(decisions_path), source_as_of, imported_timestamp
    )

    return {
        "positions": position_count,
        "investor_profiles": 1,
        "decisions": decision_count,
    }


def import_legacy_watchlist(
    connection: sqlite3.Connection,
    watchlist_path: Path,
    imported_at: Optional[datetime] = None,
    manage_transaction: bool = True,
) -> int:
    """Import the old self-selected stock pool without treating its prices as current."""
    if manage_transaction:
        with connection:
            return _import_legacy_watchlist_inner(connection, watchlist_path, imported_at)
    return _import_legacy_watchlist_inner(connection, watchlist_path, imported_at)


def _import_legacy_watchlist_inner(
    connection: sqlite3.Connection,
    watchlist_path: Path,
    imported_at: Optional[datetime] = None,
) -> int:
    watchlist_path = watchlist_path.resolve()
    if not watchlist_path.is_file():
        raise FileNotFoundError("Missing legacy watchlist input: " + str(watchlist_path))
    import_key = "legacy-watchlist:" + str(watchlist_path)
    existing_run = connection.execute(
        "SELECT id FROM import_runs WHERE source_path = ?", (import_key,)
    ).fetchone()
    if existing_run is not None:
        return 0

    records = json.loads(watchlist_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Legacy watchlist must contain a JSON list.")
    imported_timestamp = (imported_at or datetime.now(timezone.utc)).isoformat()
    source_path = str(watchlist_path)

    connection.execute(
        """
        INSERT INTO import_runs (source_path, source_as_of, imported_at, status, details)
        VALUES (?, NULL, ?, 'completed', '')
        """,
        (import_key, imported_timestamp),
    )
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Legacy watchlist contains a non-object record.")
        stock_id = _upsert_stock(connection, record)
        connection.execute(
            """
            INSERT INTO watchlist_items (
                stock_id, category, source_path, source_as_of, imported_at
            ) VALUES (?, 'legacy_watchlist', ?, NULL, ?)
            """,
            (stock_id, source_path, imported_timestamp),
        )
    return len(records)


def import_legacy_financial_snapshots(
    connection: sqlite3.Connection,
    source_path: Path,
    imported_at: Optional[datetime] = None,
    manage_transaction: bool = True,
) -> int:
    """Preserve legacy financial records as dated snapshots rather than current facts."""
    if manage_transaction:
        with connection:
            return _import_legacy_financial_snapshots_inner(
                connection, source_path, imported_at
            )
    return _import_legacy_financial_snapshots_inner(connection, source_path, imported_at)


def _import_legacy_financial_snapshots_inner(
    connection: sqlite3.Connection,
    source_path: Path,
    imported_at: Optional[datetime] = None,
) -> int:
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError("Missing legacy financial input: " + str(source_path))
    import_key = "legacy-financials:" + str(source_path)
    if connection.execute("SELECT id FROM import_runs WHERE source_path = ?", (import_key,)).fetchone():
        return 0
    records = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    timestamp = (imported_at or datetime.now(timezone.utc)).isoformat()
    connection.execute(
        "INSERT INTO import_runs (source_path, source_as_of, imported_at, status, details) VALUES (?, NULL, ?, 'completed', '')",
        (import_key, timestamp),
    )
    for record in records:
        code = _as_optional_text(record.get("code"))
        name = _as_optional_text(record.get("name"))
        if not code or not name:
            raise ValueError("Legacy financial record is missing code or name.")
        stock_id = _upsert_stock(connection, {"symbol": code, "name": name, "sector": record.get("sector")})
        connection.execute(
            """
            INSERT INTO financial_snapshots (stock_id, source, observed_at, data_json, source_path, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (stock_id, _as_optional_text(record.get("source")) or "legacy", _as_optional_text(record.get("timestamp")), json.dumps(record, ensure_ascii=False), str(source_path), timestamp),
        )
    return len(records)


def _require_files(*paths: Path) -> None:
    missing_paths = [str(path) for path in paths if not path.is_file()]
    if missing_paths:
        raise FileNotFoundError("Missing legacy migration inputs: " + ", ".join(missing_paths))


def _import_investor_profile(
    connection: sqlite3.Connection,
    profile_text: str,
    source_path: str,
    source_as_of: Optional[str],
    imported_at: str,
) -> None:
    fields = _markdown_fields(profile_text, PROFILE_FIELD)
    connection.execute(
        """
        INSERT INTO investor_profiles (
            profile_type, investment_horizon, risk_preference, profile_text,
            source_path, source_as_of, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fields.get("投资者类型", "未知"),
            fields.get("投资周期"),
            fields.get("风险偏好"),
            profile_text,
            source_path,
            source_as_of,
            imported_at,
        ),
    )


def _import_portfolio(
    connection: sqlite3.Connection,
    portfolio: Dict[str, object],
    source_path: str,
    source_as_of: Optional[str],
    imported_at: str,
) -> int:
    positions_container = portfolio.get("positions")
    if not isinstance(positions_container, dict):
        raise ValueError("Legacy portfolio does not contain a positions object.")
    positions = positions_container.get("positions")
    if not isinstance(positions, list):
        raise ValueError("Legacy portfolio positions must be a list.")

    total_market_value = sum(
        _as_float(position.get("market_value"))
        for position in positions
        if isinstance(position, dict)
    )
    cursor = connection.execute(
        """
        INSERT INTO portfolio_snapshots (
            as_of_date, currency, market_value, cash_value, source_path, source_as_of, imported_at
        ) VALUES (?, ?, ?, 0, ?, ?, ?)
        """,
        (
            source_as_of or "unknown",
            str(portfolio.get("currency") or "CNY"),
            total_market_value,
            source_path,
            source_as_of,
            imported_at,
        ),
    )
    snapshot_id = int(cursor.lastrowid)

    inserted_count = 0
    for position in positions:
        if not isinstance(position, dict):
            raise ValueError("Legacy portfolio contains a non-object position.")
        stock_id = _upsert_stock(connection, position)
        connection.execute(
            """
            INSERT INTO portfolio_positions (
                snapshot_id, stock_id, shares, shares_available, cost_price, current_price,
                market_value, pnl, pnl_pct, risk_level, dynamic_rating_json, thesis, review_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                stock_id,
                _as_float(position.get("shares")),
                _as_float(position.get("shares_available")),
                _as_optional_float(position.get("cost_price")),
                _as_optional_float(position.get("current_price")),
                _as_optional_float(position.get("market_value")),
                _as_optional_float(position.get("pnl")),
                _as_optional_float(position.get("pnl_pct")),
                _as_optional_text(position.get("risk_level")),
                json.dumps(position.get("dynamic_rating"), ensure_ascii=False),
                _as_optional_text(position.get("thesis")),
                _as_optional_text(position.get("review_date")),
            ),
        )
        inserted_count += 1
    return inserted_count


def _upsert_stock(connection: sqlite3.Connection, position: Dict[str, object]) -> int:
    symbol = _required_text(position, "symbol")
    name = _required_text(position, "name")
    connection.execute(
        """
        INSERT INTO stocks (symbol, name, exchange, sector, industry)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            name = excluded.name,
            exchange = COALESCE(stocks.exchange, excluded.exchange),
            sector = COALESCE(stocks.sector, excluded.sector),
            industry = COALESCE(stocks.industry, excluded.industry)
        """,
        (
            symbol,
            name,
            _as_optional_text(position.get("market")),
            _as_optional_text(position.get("sector")),
            _as_optional_text(position.get("industry")),
        ),
    )
    row = connection.execute("SELECT id FROM stocks WHERE symbol = ?", (symbol,)).fetchone()
    return int(row["id"])


def _import_decisions(
    connection: sqlite3.Connection,
    decisions_text: str,
    source_path: str,
    source_as_of: Optional[str],
    imported_at: str,
) -> int:
    headings = list(DECISION_HEADING.finditer(decisions_text))
    inserted_count = 0
    for index, heading in enumerate(headings):
        content_end = headings[index + 1].start() if index + 1 < len(headings) else len(decisions_text)
        content = decisions_text[heading.end() : content_end]
        if heading.group("number") == "007":
            inserted_count += _import_two_symbol_plan_records(
                connection, content, source_path, source_as_of, imported_at, heading.group("number")
            )
            continue
        fields = _markdown_fields(content, TABLE_FIELD)
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO decisions (
                legacy_key, decision_date, symbol, action, price_text, position_text,
                investment_reason, thesis, validation_metrics, maximum_risk,
                invalid_conditions, expected_horizon, outcome_text, source_path,
                source_as_of, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                heading.group("number"),
                fields.get("日期"),
                fields.get("股票"),
                fields.get("动作"),
                fields.get("价格"),
                fields.get("仓位"),
                fields.get("投资理由"),
                fields.get("核心假设"),
                fields.get("验证指标"),
                fields.get("最大风险"),
                fields.get("失败条件"),
                fields.get("预期时间"),
                fields.get("实际结果") or fields.get("实际结果（截至 2026-08-07）"),
                source_path,
                source_as_of,
                imported_at,
            ),
        )
        inserted_count += cursor.rowcount
    return inserted_count


def _repair_legacy_decision_007(
    connection: sqlite3.Connection,
    decisions_text: str,
    source_path: str,
    source_as_of: Optional[str],
    imported_at: str,
) -> None:
    """Replace only the known malformed aggregate legacy record with sourced plan records."""
    malformed = connection.execute(
        "SELECT id FROM decisions WHERE legacy_key = '007'"
    ).fetchone()
    if malformed is None:
        return
    heading = next((item for item in DECISION_HEADING.finditer(decisions_text) if item.group("number") == "007"), None)
    if heading is None:
        raise ValueError("Legacy decision #007 is missing from the source journal.")
    connection.execute("DELETE FROM decisions WHERE legacy_key = '007'")
    _import_two_symbol_plan_records(connection, decisions_text[heading.end() :], source_path, source_as_of, imported_at, "007")


def _import_two_symbol_plan_records(
    connection: sqlite3.Connection,
    content: str,
    source_path: str,
    source_as_of: Optional[str],
    imported_at: str,
    decision_number: str,
) -> int:
    fields = _two_symbol_markdown_fields(content)
    required_fields = ["决策日期", "动作", "代码", "挂单价", "持仓", "建仓 thesis", "本周内验证", "失败条件", "90 日内 review"]
    missing_fields = [field for field in required_fields if field not in fields]
    if missing_fields:
        raise ValueError("Legacy decision #007 is missing fields: " + ", ".join(missing_fields))
    inserted_count = 0
    for index in range(2):
        symbol = _clean_markdown_text(fields["代码"][index])
        decision_date = _date_from_legacy_text(fields["决策日期"][index])
        action = "计划" + _clean_markdown_text(fields["动作"][index])
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO decisions (
                legacy_key, decision_date, symbol, action, price_text, position_text,
                investment_reason, thesis, validation_metrics, maximum_risk,
                invalid_conditions, expected_horizon, outcome_text, source_path,
                source_as_of, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, NULL, ?, ?, ?)
            """,
            (
                decision_number + "-" + symbol,
                decision_date,
                symbol,
                action,
                _clean_markdown_text(fields["挂单价"][index]),
                _clean_markdown_text(fields["持仓"][index]),
                _clean_markdown_text(fields["建仓 thesis"][index]),
                _clean_markdown_text(fields["本周内验证"][index]),
                _clean_markdown_text(fields["失败条件"][index]),
                "90 日内复核：" + _date_from_legacy_text(fields["90 日内 review"][index]),
                source_path,
                source_as_of,
                imported_at,
            ),
        )
        inserted_count += cursor.rowcount
    return inserted_count


def _markdown_fields(text: str, pattern: re.Pattern) -> Dict[str, str]:
    return {match.group("field").strip(): match.group("value").strip() for match in pattern.finditer(text)}


def _two_symbol_markdown_fields(text: str) -> Dict[str, tuple]:
    return {
        match.group("field").strip(): (match.group("first").strip(), match.group("second").strip())
        for match in TWO_SYMBOL_TABLE_FIELD.finditer(text)
    }


def _clean_markdown_text(value: str) -> str:
    return value.replace("**", "").strip()


def _date_from_legacy_text(value: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if match is None:
        raise ValueError("Expected YYYY-MM-DD date in legacy decision field.")
    return match.group(0)


def _required_text(values: Dict[str, object], field: str) -> str:
    value = _as_optional_text(values.get(field))
    if not value:
        raise ValueError("Legacy portfolio position is missing " + field + ".")
    return value


def _as_optional_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: object) -> float:
    converted_value = _as_optional_float(value)
    if converted_value is None:
        raise ValueError("Expected a numeric value in legacy portfolio.")
    return converted_value


def _as_optional_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)
