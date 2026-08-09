import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.stock_master import (
    StockMetadataError,
    main as stock_master_cli_main,
    upsert_stock_record,
)


class StubStockMetadataProvider:
    def get_stock_metadata(self, symbol):
        return {
            "name": "浦发银行",
            "exchange": "SH",
            "sector": None,
            "industry": "银行",
        }


class FailingStockMetadataProvider:
    def get_stock_metadata(self, symbol):
        raise StockMetadataError("upstream unavailable")


class StockMasterTests(unittest.TestCase):
    def test_upsert_creates_new_stock_with_enriched_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)

            result = upsert_stock_record(
                connection,
                "600000.SH",
                provider=StubStockMetadataProvider(),
            )

            self.assertEqual("created", result["status"])
            self.assertEqual("浦发银行", result["stock"]["name"])
            self.assertEqual("SH", result["stock"]["exchange"])
            self.assertEqual("银行", result["stock"]["industry"])

    def test_upsert_updates_existing_stock_without_replacing_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)
            with connection:
                connection.execute(
                    "INSERT INTO stocks (symbol, name, exchange) VALUES ('600000.SH', '浦发', 'SH')"
                )

            result = upsert_stock_record(
                connection,
                "600000.SH",
                provider=StubStockMetadataProvider(),
            )

            self.assertEqual("updated", result["status"])
            self.assertEqual("浦发", result["stock"]["name"])
            self.assertEqual("银行", result["stock"]["industry"])

    def test_upsert_requires_name_when_provider_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)

            with self.assertRaises(ValueError):
                upsert_stock_record(
                    connection,
                    "600000.SH",
                    provider=FailingStockMetadataProvider(),
                )

    def test_upsert_creates_with_provider_failure_when_name_is_provided(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            connection = connect(Path(temporary_directory) / "atlas.db")
            self.addCleanup(connection.close)
            initialize_database(connection)

            result = upsert_stock_record(
                connection,
                "600000.SH",
                name="浦发银行",
                provider=FailingStockMetadataProvider(),
            )

            self.assertEqual("created", result["status"])
            self.assertEqual("浦发银行", result["stock"]["name"])
            self.assertEqual("SH", result["stock"]["exchange"])

    def test_cli_creates_stock_and_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "atlas.db"
            connection = connect(database_path)
            initialize_database(connection)
            connection.close()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = stock_master_cli_main(
                    [
                        "--database",
                        str(database_path),
                        "--symbol",
                        "600000.SH",
                        "--name",
                        "浦发银行",
                    ],
                    provider=StubStockMetadataProvider(),
                )
            result = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual("created", result["status"])
        self.assertEqual("600000.SH", result["stock"]["symbol"])


if __name__ == "__main__":
    unittest.main()
