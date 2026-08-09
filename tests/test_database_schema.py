import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import (
    _apply_pending_migrations,
    get_applied_migrations,
    initialize_database,
)


class DatabaseSchemaTests(unittest.TestCase):
    def test_initialize_database_creates_required_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)

            initialize_database(connection)

            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

        self.assertTrue(
            {
                "investor_profiles",
                "risk_budget_versions",
                "stocks",
                "portfolio_snapshots",
                "portfolio_positions",
                "watchlist_items",
                "decisions",
                "import_runs",
                "financial_metrics",
                "market_quote_cache",
                "market_breadth_cache",
                "schema_migrations",
            }.issubset(table_names)
        )
        migrations = get_applied_migrations(connection)
        self.assertEqual(["001_initial_schema"], [item["version"] for item in migrations])

    def test_initialize_database_is_idempotent_and_records_migration_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)

            initialize_database(connection)
            first = get_applied_migrations(connection)
            initialize_database(connection)
            second = get_applied_migrations(connection)

            self.assertEqual(1, len(first))
            self.assertEqual(1, len(second))
            self.assertEqual(first[0]["version"], second[0]["version"])

    def test_pending_migrations_apply_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)
            calls = []

            def first_migration(cursor) -> None:
                calls.append("first")
                cursor.execute("CREATE TABLE migration_first (id INTEGER PRIMARY KEY)")

            def second_migration(cursor) -> None:
                calls.append("second")
                cursor.execute("CREATE TABLE migration_second (id INTEGER PRIMARY KEY)")

            with connection:
                _apply_pending_migrations(
                    connection,
                    [
                        {"version": "002_test_first", "description": "first", "apply": first_migration},
                        {"version": "003_test_second", "description": "second", "apply": second_migration},
                    ],
                )

            versions = [item["version"] for item in get_applied_migrations(connection)]
            self.assertEqual(["001_initial_schema", "002_test_first", "003_test_second"], versions)
            self.assertEqual(["first", "second"], calls)

    def test_failed_migration_rolls_back_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)

            def broken_migration(cursor) -> None:
                cursor.execute("CREATE TABLE should_rollback (id INTEGER PRIMARY KEY)")
                raise RuntimeError("boom")

            with connection:
                with self.assertRaises(RuntimeError):
                    _apply_pending_migrations(
                        connection,
                        [{"version": "002_broken", "description": "broken", "apply": broken_migration}],
                    )

            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            versions = [item["version"] for item in get_applied_migrations(connection)]
            self.assertNotIn("should_rollback", table_names)
            self.assertNotIn("002_broken", versions)

    def test_connection_enforces_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO portfolio_positions (snapshot_id, stock_id, shares) "
                    "VALUES (999, 999, 1)"
                )


if __name__ == "__main__":
    unittest.main()
