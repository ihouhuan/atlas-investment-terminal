import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    source_as_of TEXT,
    imported_at TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS investor_profiles (
    id INTEGER PRIMARY KEY,
    profile_type TEXT NOT NULL,
    investment_horizon TEXT,
    risk_preference TEXT,
    profile_text TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_as_of TEXT,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_budget_versions (
    id INTEGER PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    rules_json TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_as_of TEXT,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stocks (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    exchange TEXT,
    sector TEXT,
    industry TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY,
    as_of_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    market_value REAL,
    cash_value REAL,
    source_path TEXT NOT NULL,
    source_as_of TEXT,
    imported_at TEXT NOT NULL,
    UNIQUE (as_of_date, source_path)
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES portfolio_snapshots(id),
    stock_id INTEGER NOT NULL REFERENCES stocks(id),
    shares REAL NOT NULL,
    shares_available REAL,
    cost_price REAL,
    current_price REAL,
    market_value REAL,
    pnl REAL,
    pnl_pct REAL,
    risk_level TEXT,
    dynamic_rating_json TEXT,
    thesis TEXT,
    review_date TEXT,
    UNIQUE (snapshot_id, stock_id)
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id INTEGER PRIMARY KEY,
    stock_id INTEGER NOT NULL REFERENCES stocks(id),
    category TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_as_of TEXT,
    imported_at TEXT NOT NULL,
    UNIQUE (stock_id, source_path)
);

CREATE TABLE IF NOT EXISTS financial_snapshots (
    id INTEGER PRIMARY KEY,
    stock_id INTEGER NOT NULL REFERENCES stocks(id),
    source TEXT NOT NULL,
    observed_at TEXT,
    data_json TEXT NOT NULL,
    source_path TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_metrics (
    id INTEGER PRIMARY KEY,
    stock_id INTEGER NOT NULL REFERENCES stocks(id),
    report_date TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE (stock_id, report_date, metric_key, source)
);

CREATE INDEX IF NOT EXISTS idx_financial_metrics_stock_report
ON financial_metrics (stock_id, report_date);

CREATE TABLE IF NOT EXISTS market_quote_cache (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    price REAL,
    previous_close REAL,
    change REAL,
    change_pct REAL,
    observed_at TEXT,
    fetched_at TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thesis_versions (
    id INTEGER PRIMARY KEY,
    stock_id INTEGER NOT NULL REFERENCES stocks(id),
    thesis TEXT NOT NULL,
    validation_metrics TEXT NOT NULL,
    invalid_conditions TEXT NOT NULL,
    review_date TEXT NOT NULL,
    entry_source TEXT NOT NULL,
    source_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY,
    legacy_key TEXT NOT NULL UNIQUE,
    decision_date TEXT,
    symbol TEXT,
    action TEXT,
    price_text TEXT,
    position_text TEXT,
    investment_reason TEXT,
    thesis TEXT,
    validation_metrics TEXT,
    maximum_risk TEXT,
    invalid_conditions TEXT,
    expected_horizon TEXT,
    outcome_text TEXT,
    source_path TEXT NOT NULL,
    source_as_of TEXT,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_updates (
    id INTEGER PRIMARY KEY,
    decision_id INTEGER NOT NULL REFERENCES decisions(id),
    event_type TEXT NOT NULL,
    execution_date TEXT,
    execution_price TEXT,
    actual_result TEXT,
    review_notes TEXT,
    source_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS morning_brief_snapshots (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    risk_violation_count INTEGER NOT NULL,
    missing_thesis_count INTEGER NOT NULL,
    unconfirmed_plan_count INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    research_conclusion TEXT,
    review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed', 'reviewed')),
    reviewed_at TEXT,
    review_notes TEXT
);

CREATE TABLE IF NOT EXISTS morning_brief_follow_up_actions (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES morning_brief_snapshots(id),
    action_text TEXT NOT NULL,
    decision_legacy_key TEXT,
    due_date TEXT,
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('high', 'normal', 'low')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS alert_acknowledgements (
    alert_key TEXT PRIMARY KEY,
    acknowledged_at TEXT NOT NULL
);

"""


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the Atlas schema atomically and leave foreign keys enabled."""
    with connection:
        connection.executescript(SCHEMA)
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(morning_brief_snapshots)").fetchall()
        }
        if "research_conclusion" not in columns:
            connection.execute("ALTER TABLE morning_brief_snapshots ADD COLUMN research_conclusion TEXT")
        if "review_status" not in columns:
            connection.execute(
                "ALTER TABLE morning_brief_snapshots ADD COLUMN review_status TEXT NOT NULL DEFAULT 'unreviewed'"
            )
        if "reviewed_at" not in columns:
            connection.execute("ALTER TABLE morning_brief_snapshots ADD COLUMN reviewed_at TEXT")
        if "review_notes" not in columns:
            connection.execute("ALTER TABLE morning_brief_snapshots ADD COLUMN review_notes TEXT")
        action_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(morning_brief_follow_up_actions)").fetchall()
        }
        if "due_date" not in action_columns:
            connection.execute("ALTER TABLE morning_brief_follow_up_actions ADD COLUMN due_date TEXT")
        if "priority" not in action_columns:
            connection.execute(
                "ALTER TABLE morning_brief_follow_up_actions ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'"
            )
        connection.execute("PRAGMA foreign_keys = ON")
