import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "store.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  tagline TEXT DEFAULT '',
  rating REAL DEFAULT 0,
  city TEXT DEFAULT '',
  address TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  email TEXT DEFAULT '',
  opens_at TEXT DEFAULT '09:30',
  closes_at TEXT DEFAULT '21:30',
  lat REAL, lng REAL,
  accent_color TEXT DEFAULT '#3d5afe'
);

CREATE TABLE IF NOT EXISTS branches (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  address TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  name TEXT NOT NULL,
  brand TEXT DEFAULT '',
  category TEXT DEFAULT '',
  description TEXT DEFAULT '',
  -- Words a shopper might use that appear nowhere else on the record:
  -- "shoes" for a trainer, "charger" for an adapter. Without these, a search
  -- for "Nike shoes" finds nothing, because no field contains "shoes".
  tags TEXT DEFAULT '',
  image_url TEXT DEFAULT '',
  rating REAL DEFAULT 0,
  rating_count INTEGER DEFAULT 0,
  popularity INTEGER DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  store_id TEXT NOT NULL,
  sku TEXT NOT NULL UNIQUE,
  barcode TEXT UNIQUE,
  label TEXT DEFAULT '',            -- "Black - Size 9"
  price REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Stock lives per variant per branch. Availability is on_hand - reserved, and
-- freshness comes from updated_at, which is what drives the status colours.
CREATE TABLE IF NOT EXISTS inventory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  branch_id TEXT NOT NULL,
  variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
  on_hand INTEGER NOT NULL DEFAULT 0 CHECK(on_hand >= 0),
  reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(branch_id, variant_id)
);

-- Append-only activity log. Analytics and the dashboard read from here rather
-- than from mutated totals, so every number can be traced to the event that
-- caused it.
--
-- Reservation lifecycle steps are logged too, with zero deltas. Accepting a
-- reservation moves no stock, but it belongs on the product's timeline -- the
-- history is meant to explain how a count got where it is, and "accepted" is
-- part of that story.
CREATE TABLE IF NOT EXISTS inventory_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  branch_id TEXT NOT NULL,
  variant_id INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN
    ('STOCK_RECEIVED','STOCK_ADJUSTMENT','SALE','RETURN',
     'RESERVATION','RESERVATION_ACCEPTED','RESERVATION_READY',
     'RESERVATION_RELEASE','PICKUP')),
  quantity INTEGER NOT NULL DEFAULT 0,
  on_hand_delta INTEGER NOT NULL DEFAULT 0,
  reserved_delta INTEGER NOT NULL DEFAULT 0,
  reservation_id INTEGER,
  note TEXT DEFAULT '',
  actor TEXT DEFAULT 'system',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  name TEXT NOT NULL,
  phone TEXT DEFAULT '',
  email TEXT DEFAULT '',
  is_demo INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS employees (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'staff',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,        -- RSV-48291
  store_id TEXT NOT NULL,
  branch_id TEXT NOT NULL,
  variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN
    ('pending','accepted','ready_for_pickup','completed','rejected','expired','cancelled')),
  note TEXT DEFAULT '',
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Historical rows snapshot name and price: deleting a product must never
-- rewrite what somebody paid for it.
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  branch_id TEXT NOT NULL,
  customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
  variant_id INTEGER REFERENCES product_variants(id) ON DELETE SET NULL,
  reservation_id INTEGER REFERENCES reservations(id) ON DELETE SET NULL,
  product_name TEXT NOT NULL,
  sku TEXT DEFAULT '',
  unit_price REAL NOT NULL DEFAULT 0,
  quantity INTEGER NOT NULL DEFAULT 1,
  total REAL NOT NULL DEFAULT 0,
  channel TEXT NOT NULL DEFAULT 'in-store',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Mock only: no real processing happens (spec section 22).
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
  method TEXT NOT NULL DEFAULT 'cash',
  amount REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'captured',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
  number TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wishlists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(customer_id, product_id)
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id TEXT NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  variant_id INTEGER REFERENCES product_variants(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'back_in_stock',
  title TEXT DEFAULT '',
  body TEXT DEFAULT '',
  fired_at TEXT,
  seen_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_variants_product ON product_variants(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_variant ON inventory(variant_id);
CREATE INDEX IF NOT EXISTS idx_movements_variant ON inventory_movements(variant_id);
CREATE INDEX IF NOT EXISTS idx_reservations_status ON reservations(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
"""


def connect():
    """A connection for the current caller.

    check_same_thread is off because Flask serves on several threads; each call
    opens its own connection rather than sharing one, so that is safe.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Bumped whenever the schema changes shape. Everything in this database is
# regenerated demo data, so a mismatch is resolved by rebuilding rather than by
# writing a migration for data nobody needs to keep.
SCHEMA_VERSION = 2

TABLES = [
    "notifications", "wishlists", "invoices", "payments", "orders",
    "reservations", "inventory_movements", "inventory", "product_variants",
    "products", "employees", "customers", "branches", "stores",
]


def init():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        has_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='products'").fetchone()

        if has_tables and current != SCHEMA_VERSION:
            _drop_all(conn)

        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()


def _drop_all(conn):
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.execute("PRAGMA foreign_keys = ON")


def reset():
    """Wipe everything and recreate the empty schema.

    Backs the Reset Demo button: a showcase has to be repeatable, so the same
    walkthrough can be given twice without the stock having drifted.
    """
    conn = connect()
    try:
        _drop_all(conn)
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
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
    """Run a single write. Returns (rows_affected, last_insert_id)."""
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount, cur.lastrowid
    finally:
        conn.close()


def transaction():
    """Connection for multi-statement writes that must land together.

    Stock moves and reservation state changes have to be atomic -- a hold that
    is recorded without the matching reserved count is a real inventory bug.

    Usage:
        with db.transaction() as conn:
            conn.execute(...)
    """
    return _Transaction()


class _Transaction:
    def __enter__(self):
        self.conn = connect()
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        return False
