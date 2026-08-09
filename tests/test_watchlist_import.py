import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.legacy_import import import_legacy_watchlist


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WATCHLIST_PATH = PROJECT_ROOT / "legacy" / "openclaw-atlas" / "china_market" / "data" / "user_watchlist.json"


class WatchlistImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection = connect(Path(self.temporary_directory.name) / "atlas.db")
        initialize_database(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_imports_legacy_watchlist_with_source(self) -> None:
        inserted_count = import_legacy_watchlist(self.connection, WATCHLIST_PATH)

        watchlist_item = self.connection.execute(
            """
            SELECT stocks.symbol, watchlist_items.category, watchlist_items.source_path
            FROM watchlist_items
            JOIN stocks ON stocks.id = watchlist_items.stock_id
            WHERE stocks.symbol = '601899.SH'
            """
        ).fetchone()

        self.assertEqual(87, inserted_count)
        self.assertEqual("legacy_watchlist", watchlist_item["category"])
        self.assertTrue(watchlist_item["source_path"].endswith("user_watchlist.json"))

    def test_watchlist_import_is_idempotent(self) -> None:
        import_legacy_watchlist(self.connection, WATCHLIST_PATH)

        self.assertEqual(0, import_legacy_watchlist(self.connection, WATCHLIST_PATH))
        self.assertEqual(
            87,
            self.connection.execute("SELECT COUNT(*) FROM watchlist_items").fetchone()[0],
        )


if __name__ == "__main__":
    unittest.main()
