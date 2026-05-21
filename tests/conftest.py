import pytest
import sqlite3
from pathlib import Path
from whereabout.db import apply_pending_migrations


@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    """Return an in-memory-style SQLite connection backed by a temp file with migrations applied."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    apply_pending_migrations(conn)
    yield conn
    conn.close()
