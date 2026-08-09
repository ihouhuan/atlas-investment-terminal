import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.initialize_atlas import initialize_atlas_database
from backend.services.thesis import build_thesis_overview


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class ThesisTests(unittest.TestCase):
    def test_marks_placeholder_theses_as_needing_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)

            overview = build_thesis_overview(connection)

        self.assertEqual(3, overview["total"])
        self.assertEqual(3, overview["needs_definition_count"])
        first_item = overview["items"][0]
        self.assertEqual("needs_definition", first_item["status"])
        self.assertEqual("待补充（用户未提供）", first_item["thesis"])
        self.assertTrue(first_item["source_path"].endswith("portfolio.json"))


if __name__ == "__main__":
    unittest.main()
