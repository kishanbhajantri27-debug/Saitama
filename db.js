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

CREATE TABLE IF NOT EXISTS waitlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
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

module.exports = db;
