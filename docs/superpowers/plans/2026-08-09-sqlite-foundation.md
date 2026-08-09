# Atlas SQLite Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a testable SQLite foundation that imports legacy Atlas portfolio, investor profile, decisions, and one canonical risk-budget version.

**Architecture:** Keep persistence in `backend/database`, domain operations in `backend/services`, and legacy content read-only under `legacy/`. Store source provenance with every imported financial record and make imports idempotent.

**Tech Stack:** Python 3.12+, standard-library `sqlite3`, `json`, `pathlib`, `datetime`, `unittest`.

## Global Constraints

- No brokerage integration, order placement, automatic trading, or direct buy/sell recommendation.
- `legacy/openclaw-atlas/` is read-only migration input.
- Store source path, source-as-of date, and import timestamp for every migrated asset.
- The tiered A-share budget is the sole active risk rule; old rating-based limits remain historical only.
- Run `python -m unittest discover -s tests -v` after every task.

---

### Task 1: Database schema and connection

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/database/__init__.py`
- Create: `backend/database/connection.py`
- Create: `backend/database/schema.py`
- Create: `tests/test_database_schema.py`

**Interfaces:**
- Produces `connect(database_path: Path) -> sqlite3.Connection`.
- Produces `initialize_database(connection: sqlite3.Connection) -> None`.

- [ ] Write failing schema tests for table creation and foreign-key enforcement.
- [ ] Run `python -m unittest tests.test_database_schema -v`; expect missing-module failure.
- [ ] Implement connection and schema with transactions.
- [ ] Run the schema test; expect pass.

### Task 2: Canonical risk budget service

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/risk_budget.py`
- Create: `tests/test_risk_budget.py`

**Interfaces:**
- Produces `CANONICAL_RISK_BUDGET` and `install_canonical_risk_budget(connection, source_path, source_as_of) -> int`.
- Produces `get_active_risk_budget(connection) -> dict`.

- [ ] Write failing tests asserting tier limits, only one active version, and idempotent installation.
- [ ] Run `python -m unittest tests.test_risk_budget -v`; expect missing-module failure.
- [ ] Implement the service using `risk_budget_versions`.
- [ ] Run the test; expect pass.

### Task 3: Legacy asset importer

**Files:**
- Create: `backend/services/legacy_import.py`
- Create: `tests/test_legacy_import.py`

**Interfaces:**
- Produces `import_legacy_atlas(connection, legacy_root: Path, imported_at: datetime | None = None) -> dict[str, int]`.
- Consumes `portfolio/portfolio.json`, `投资者档案/投资者档案.md`, and `决策日志/决策日志.md`.

- [ ] Write failing tests using copied fixture files and asserting three positions, one investor profile, decisions, provenance, and idempotence.
- [ ] Run `python -m unittest tests.test_legacy_import -v`; expect missing-module failure.
- [ ] Implement strict JSON and Markdown extraction without inventing missing values.
- [ ] Run the test; expect pass.

### Task 4: Initialization command and full validation

**Files:**
- Create: `backend/services/initialize_atlas.py`
- Create: `tests/test_initialize_atlas.py`
- Modify: `README.md`

**Interfaces:**
- Produces `initialize_atlas_database(database_path: Path, legacy_root: Path) -> dict[str, int]`.

- [ ] Write a failing integration test that creates a temporary database from legacy assets.
- [ ] Run `python -m unittest tests.test_initialize_atlas -v`; expect missing-module failure.
- [ ] Implement initialization orchestration and document the local command.
- [ ] Run `python -m unittest discover -s tests -v`; expect all tests to pass.
