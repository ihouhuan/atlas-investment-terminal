import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.services.decision_journal import build_decision_journal, create_decision_update, get_decision_updates
from backend.services.initialize_atlas import initialize_atlas_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "legacy" / "openclaw-atlas"


class DecisionUpdateTests(unittest.TestCase):
    def test_appends_updates_and_exposes_latest_event_without_overwriting_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            initialize_atlas_database(database_path, LEGACY_ROOT)
            connection = connect(database_path)
            self.addCleanup(connection.close)

            create_decision_update(
                connection, "007-600693.SH", "not_executed", "2026-08-11", None,
                "未成交", "挂单当日未执行", "首次补录", created_at="2026-08-11T08:00:00+00:00"
            )
            create_decision_update(
                connection, "007-600693.SH", "reviewed", None, None,
                "未成交，继续观察", "复盘：原计划未执行", "复盘更新", created_at="2026-08-12T08:00:00+00:00"
            )
            journal = build_decision_journal(connection)
            history = get_decision_updates(connection, "007-600693.SH")

        item = next(record for record in journal["items"] if record["legacy_key"] == "007-600693.SH")
        self.assertEqual(2, history["total"])
        self.assertEqual("reviewed", item["latest_update"]["event_type"])
        self.assertEqual("复盘：原计划未执行", item["latest_update"]["review_notes"])
        self.assertEqual("计划挂单卖出（限价单）", item["action"])


if __name__ == "__main__":
    unittest.main()
