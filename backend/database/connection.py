from pathlib import Path
import sqlite3


def connect(database_path: Path) -> sqlite3.Connection:
    """Open an Atlas SQLite database with integrity safeguards enabled."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
