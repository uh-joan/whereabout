import sqlite3
import importlib.resources
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path.home() / ".local" / "share" / "whereabout" / "whereabout.db"


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    apply_pending_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()


def apply_pending_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    migrations_dir = Path(__file__).parent / "migrations"
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        name = sql_file.name
        row = conn.execute("SELECT 1 FROM migrations WHERE name = ?", (name,)).fetchone()
        if row is None:
            conn.executescript(sql_file.read_text())
            conn.execute("INSERT INTO migrations(name) VALUES (?)", (name,))
            conn.commit()
