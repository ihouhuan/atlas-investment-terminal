import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.seed_ui_smoke import seed_ui_smoke_cache


class SeedUiSmokeCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self._temporary_directory.name) / "atlas.db"

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_seed_inserts_breadth_and_index_quotes(self) -> None:
        seed_ui_smoke_cache(self.database_path)

        connection = connect(self.database_path)
        try:
            breadth = connection.execute(
                "SELECT advancers, limit_up, source FROM market_breadth_cache"
            ).fetchone()
            quotes = connection.execute(
                "SELECT COUNT(*) FROM market_quote_cache WHERE source = 'ui-smoke-fixture'"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(2830, breadth["advancers"])
        self.assertEqual(42, breadth["limit_up"])
        self.assertEqual("ui-smoke-fixture", breadth["source"])
        self.assertEqual(3, quotes)

    def test_seed_is_idempotent(self) -> None:
        seed_ui_smoke_cache(self.database_path)
        seed_ui_smoke_cache(self.database_path)

        connection = connect(self.database_path)
        try:
            breadth_count = connection.execute(
                "SELECT COUNT(*) FROM market_breadth_cache"
            ).fetchone()[0]
            quote_count = connection.execute(
                "SELECT COUNT(*) FROM market_quote_cache WHERE source = 'ui-smoke-fixture'"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(1, breadth_count)
        self.assertEqual(3, quote_count)


if __name__ == "__main__":
    unittest.main()
