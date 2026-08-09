import tempfile
import unittest
from pathlib import Path

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.risk_budget import (
    get_active_risk_budget,
    install_canonical_risk_budget,
)


class RiskBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection = connect(Path(self.temporary_directory.name) / "atlas.db")
        initialize_database(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_installs_canonical_tiered_budget(self) -> None:
        install_canonical_risk_budget(
            self.connection,
            "legacy/openclaw-atlas/portfolio/仓位预算.md",
            "2026-08-08",
        )

        budget = get_active_risk_budget(self.connection)

        self.assertEqual(0.15, budget["tiers"]["core"]["single_stock_max"])
        self.assertEqual(0.08, budget["tiers"]["growth"]["single_stock_max"])
        self.assertEqual(0.03, budget["tiers"]["thematic"]["single_stock_max"])
        self.assertEqual(0.20, budget["portfolio"]["minimum_cash"])
        self.assertEqual(0.0, budget["portfolio"]["maximum_leverage"])

    def test_install_is_idempotent_and_leaves_one_active_version(self) -> None:
        first_id = install_canonical_risk_budget(
            self.connection,
            "legacy/openclaw-atlas/portfolio/仓位预算.md",
            "2026-08-08",
        )
        second_id = install_canonical_risk_budget(
            self.connection,
            "legacy/openclaw-atlas/portfolio/仓位预算.md",
            "2026-08-08",
        )

        active_count = self.connection.execute(
            "SELECT COUNT(*) FROM risk_budget_versions WHERE is_active = 1"
        ).fetchone()[0]

        self.assertEqual(first_id, second_id)
        self.assertEqual(1, active_count)


if __name__ == "__main__":
    unittest.main()
