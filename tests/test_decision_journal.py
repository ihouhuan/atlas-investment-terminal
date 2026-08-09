import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.decision_journal import build_decision_journal
from backend.services.initialize_atlas import initialize_atlas_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class DecisionJournalTests(unittest.TestCase):
    def test_preserves_complete_records_and_marks_unexecuted_plan_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)

            journal = build_decision_journal(connection)

        self.assertEqual(7, journal["total"])
        self.assertEqual(0, journal["incomplete_import_count"])
        self.assertEqual(2, journal["planned_record_count"])
        nvda = next(item for item in journal["items"] if item["legacy_key"] == "001")
        planned_sale = next(item for item in journal["items"] if item["legacy_key"] == "007-600693.SH")
        self.assertEqual("NVDA", nvda["symbol"])
        self.assertIn("数据中心收入", nvda["thesis"])
        self.assertEqual("complete", nvda["record_status"])
        self.assertEqual("planned_record", planned_sale["record_status"])
        self.assertTrue(planned_sale["source_path"].endswith("决策日志.md"))


if __name__ == "__main__":
    unittest.main()
