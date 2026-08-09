import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.legacy_import import import_legacy_financial_snapshots


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "legacy" / "openclaw-atlas" / "china_market" / "data" / "stock_fundamentals.jsonl"


class FinancialImportTests(unittest.TestCase):
    def test_imports_jsonl_financial_snapshots_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)

            imported_count = import_legacy_financial_snapshots(connection, SOURCE_PATH)
            record = connection.execute(
                """
                SELECT financial_snapshots.source, financial_snapshots.source_path
                FROM financial_snapshots
                JOIN stocks ON stocks.id = financial_snapshots.stock_id
                WHERE stocks.symbol = '000021.SZ'
                ORDER BY financial_snapshots.id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertGreater(imported_count, 0)
        self.assertEqual("iwencai", record["source"])
        self.assertTrue(record["source_path"].endswith("stock_fundamentals.jsonl"))
