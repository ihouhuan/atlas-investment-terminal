import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.initialize_atlas import initialize_atlas_database
from backend.services.thesis import build_thesis_overview, create_thesis_version, get_thesis_versions


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class ThesisVersionTests(unittest.TestCase):
    def test_appends_manual_versions_and_uses_the_latest_one_in_overview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)

            create_thesis_version(
                connection,
                "601899.SH",
                "铜金产量增长支持自由现金流改善",
                "铜价与产量季度跟踪",
                "产量持续不及预期",
                "2026-11-08",
                "首次手动记录",
                created_at="2026-08-09T09:00:00+00:00",
            )
            create_thesis_version(
                connection,
                "601899.SH",
                "铜金产量增长仍支持自由现金流改善",
                "铜价、产量与资本开支季度跟踪",
                "产量持续不及预期或铜价显著下行",
                "2026-12-08",
                "季度更新",
                created_at="2026-08-10T09:00:00+00:00",
            )
            overview = build_thesis_overview(connection)
            history = get_thesis_versions(connection, "601899.SH")
            version_count = connection.execute(
                "SELECT COUNT(*) FROM thesis_versions"
            ).fetchone()[0]

        item = next(record for record in overview["items"] if record["symbol"] == "601899.SH")
        self.assertEqual(2, version_count)
        self.assertEqual("defined", item["status"])
        self.assertEqual("铜金产量增长仍支持自由现金流改善", item["thesis"])
        self.assertEqual("铜价、产量与资本开支季度跟踪", item["validation_metrics"])
        self.assertEqual("产量持续不及预期或铜价显著下行", item["invalid_conditions"])
        self.assertEqual("2026-12-08", item["review_date"])
        self.assertEqual("user_entry", item["entry_source"])
        self.assertEqual(2, history["total"])
        self.assertEqual("季度更新", history["items"][0]["source_note"])


if __name__ == "__main__":
    unittest.main()
