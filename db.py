"""SQLite connections for the collector (writer) and the dashboard (reader).

Only the collector writes. Everything else opens the file read-only.
"""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")
BUSY_TIMEOUT_MS = 5000


def connect_writer(path) -> sqlite3.Connection:
    """Open (and create) the database: schema if missing, WAL, busy timeout."""
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def connect_readonly(path) -> sqlite3.Connection:
    """Open an existing database for reading only (mode=ro).

    The file must already exist and be in WAL mode (the writer sets that).
    check_same_thread is off because Streamlit shares one cached connection
    between its script threads; the connection never writes.
    """
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000,
                           check_same_thread=False)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
    conn.execute("PRAGMA query_only=ON;")
    return conn
