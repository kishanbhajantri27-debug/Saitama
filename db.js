const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');

const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir);

const db = new Database(path.join(dataDir, 'shop.db'));
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
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
`);

db.prepare('INSERT OR IGNORE INTO shop_settings (id) VALUES (1)').run();

// seen_at records that the customer has actually looked at a decision, so an
// approval can be announced once and then stop nagging. Added after requests
// shipped, hence the column check rather than a plain CREATE.
const requestCols = db.prepare('PRAGMA table_info(requests)').all().map(c => c.name);
if (!requestCols.includes('seen_at')) {
  db.prepare('ALTER TABLE requests ADD COLUMN seen_at TEXT').run();
}

// The waitlist table predates approvals: every signup was implicitly pending.
// Carry those rows into requests as pending, then retire the old table. Guarded
// so it is a no-op on databases created after this change.
const hasWaitlist = db.prepare(
  "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'waitlist'"
).get();
if (hasWaitlist) {
  db.transaction(() => {
    db.prepare(
      `INSERT OR IGNORE INTO requests (item_id, customer_id, status, created_at)
       SELECT item_id, customer_id, 'pending', created_at FROM waitlist`
    ).run();
    db.prepare('DROP TABLE waitlist').run();
  })();
}

module.exports = db;
