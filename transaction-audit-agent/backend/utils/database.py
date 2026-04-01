"""
Database initialization and connection management using SQLite.
"""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "audit.db"


def get_connection():
    """Return a new SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            date    TEXT NOT NULL,
            merchant TEXT NOT NULL,
            amount  REAL NOT NULL,
            category TEXT NOT NULL,
            type    TEXT NOT NULL,
            flags   TEXT DEFAULT '[]'
        )
    """)
    conn.commit()
    conn.close()


def row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict, parsing JSON fields."""
    d = dict(row)
    if "flags" in d and isinstance(d["flags"], str):
        try:
            d["flags"] = json.loads(d["flags"])
        except (json.JSONDecodeError, TypeError):
            d["flags"] = []
    return d
