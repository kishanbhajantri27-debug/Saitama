import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "shop.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  price REAL DEFAULT 0,
  category TEXT DEFAULT '',
  image_url TEXT DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('available','upcoming')) DEFAULT 'available',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT DEFAULT '',
  email TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('pending','approved','declined')) DEFAULT 'pending',
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  responded_at TEXT,
  seen_at TEXT,
  UNIQUE(item_id, customer_id)
);

CREATE TABLE IF NOT EXISTS shop_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  shop_name TEXT NOT NULL DEFAULT 'My Shop',
  tagline TEXT DEFAULT '',
  logo_url TEXT DEFAULT '',
  accent_color TEXT DEFAULT '#2f6f4f',
  contact_phone TEXT DEFAULT '',
  contact_email TEXT DEFAULT '',
  address TEXT DEFAULT '',
  hours_text TEXT DEFAULT ''
);
"""


def connect():
    """A connection for the current caller.

    check_same_thread is off because Flask serves requests on several threads;
    each call opens its own connection rather than sharing one, so that is safe.
    WAL lets a reader work while a writer holds the file.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO shop_settings (id) VALUES (1)")

        # seen_at arrived after requests shipped, so older databases lack it.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(requests)")]
        if "seen_at" not in cols:
            conn.execute("ALTER TABLE requests ADD COLUMN seen_at TEXT")

        # The waitlist table predates approvals: every signup was implicitly
        # pending. Carry those rows over, then retire the old table. A no-op on
        # databases created after that change.
        has_waitlist = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'waitlist'"
        ).fetchone()
        if has_waitlist:
            conn.execute(
                """INSERT OR IGNORE INTO requests (item_id, customer_id, status, created_at)
                   SELECT item_id, customer_id, 'pending', created_at FROM waitlist"""
            )
            conn.execute("DROP TABLE waitlist")

        conn.commit()
    finally:
        conn.close()


def query(sql, params=()):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """Run a write. Returns (rows_affected, last_insert_id)."""
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount, cur.lastrowid
    finally:
        conn.close()
