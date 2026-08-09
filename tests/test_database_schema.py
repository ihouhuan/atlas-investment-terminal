import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import initialize_database


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
            }.issubset(table_names)
        )

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
