const path = require('path');
const crypto = require('crypto');
const express = require('express');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const db = require('./db');

const ADMIN_USER = process.env.ADMIN_USER || 'admin';
const ADMIN_PASS = process.env.ADMIN_PASS || 'changeme123';
if (!process.env.ADMIN_PASS) {
  console.warn('[shop-crm] ADMIN_PASS not set — using default admin login (admin / changeme123). Set ADMIN_USER/ADMIN_PASS in .env before sharing this publicly.');
}

function safeEqual(a, b) {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

function requireAdmin(req, res, next) {
  const header = req.headers.authorization || '';
  const [scheme, encoded] = header.split(' ');
  if (scheme === 'Basic' && encoded) {
    const decoded = Buffer.from(encoded, 'base64').toString('utf8');
    const sep = decoded.indexOf(':');
    const user = sep === -1 ? decoded : decoded.slice(0, sep);
    const pass = sep === -1 ? '' : decoded.slice(sep + 1);
    if (safeEqual(user, ADMIN_USER) && safeEqual(pass, ADMIN_PASS)) return next();
  }
  res.set('WWW-Authenticate', 'Basic realm="Shop Admin"');
  res.status(401).send('Authentication required');
}

const app = express();
app.use(express.json());
app.get('/admin.html', requireAdmin, (req, res) => res.sendFile(path.join(__dirname, 'public', 'admin.html')));
app.use(express.static(path.join(__dirname, 'public')));

function findCustomer(phone, email) {
  if (phone) {
    const byPhone = db.prepare('SELECT * FROM customers WHERE phone = ? AND phone != \'\'').get(phone);
    if (byPhone) return byPhone;
  }
  if (email) {
    const byEmail = db.prepare('SELECT * FROM customers WHERE email = ? AND email != \'\'').get(email);
    if (byEmail) return byEmail;
  }
  return null;
}

// ---------- Items ----------

app.get('/api/items', (req, res) => {
  const { status } = req.query;
  const rows = status
    ? db.prepare('SELECT * FROM items WHERE status = ? ORDER BY created_at DESC').all(status)
    : db.prepare('SELECT * FROM items ORDER BY created_at DESC').all();
  res.json(rows);
});

app.post('/api/items', requireAdmin, (req, res) => {
  const { name, description = '', price = 0, category = '', image_url = '', status = 'available' } = req.body;
  if (!name || !name.trim()) return res.status(400).json({ error: 'name is required' });
  if (!['available', 'upcoming'].includes(status)) return res.status(400).json({ error: 'invalid status' });
  const info = db.prepare(
    'INSERT INTO items (name, description, price, category, image_url, status) VALUES (?, ?, ?, ?, ?, ?)'
  ).run(name.trim(), description, Number(price) || 0, category, image_url, status);
  res.status(201).json(db.prepare('SELECT * FROM items WHERE id = ?').get(info.lastInsertRowid));
});

app.put('/api/items/:id', requireAdmin, (req, res) => {
  const existing = db.prepare('SELECT * FROM items WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'item not found' });
  const { name, description, price, category, image_url, status } = req.body;
  if (status && !['available', 'upcoming'].includes(status)) return res.status(400).json({ error: 'invalid status' });
  db.prepare(
    'UPDATE items SET name = ?, description = ?, price = ?, category = ?, image_url = ?, status = ? WHERE id = ?'
  ).run(
    name ?? existing.name,
    description ?? existing.description,
    price != null ? Number(price) : existing.price,
    category ?? existing.category,
    image_url ?? existing.image_url,
    status ?? existing.status,
    req.params.id
  );
  res.json(db.prepare('SELECT * FROM items WHERE id = ?').get(req.params.id));
});

app.delete('/api/items/:id', requireAdmin, (req, res) => {
  const info = db.prepare('DELETE FROM items WHERE id = ?').run(req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: 'item not found' });
  res.status(204).end();
});

// Pending counts for every item in one query, so the admin table does not fire
// a separate request per row.
app.get('/api/requests/counts', requireAdmin, (req, res) => {
  const rows = db.prepare(
    "SELECT item_id, COUNT(*) AS count FROM requests WHERE status = 'pending' GROUP BY item_id"
  ).all();
  res.json(Object.fromEntries(rows.map(r => [r.item_id, r.count])));
});

app.get('/api/items/:id/requests', requireAdmin, (req, res) => {
  const rows = db.prepare(
    `SELECT c.id, c.name, c.phone, c.email, r.status, r.created_at
     FROM requests r JOIN customers c ON c.id = r.customer_id
     WHERE r.item_id = ? ORDER BY r.created_at ASC`
  ).all(req.params.id);
  res.json(rows);
});

// ---------- Customers ----------

app.get('/api/customers', requireAdmin, (req, res) => {
  const rows = db.prepare(
    `SELECT c.*, GROUP_CONCAT(i.name, ', ') AS interests
     FROM customers c
     LEFT JOIN requests r ON r.customer_id = c.id
     LEFT JOIN items i ON i.id = r.item_id
     GROUP BY c.id
     ORDER BY c.created_at DESC`
  ).all();
  res.json(rows);
});

app.put('/api/customers/:id', requireAdmin, (req, res) => {
  const existing = db.prepare('SELECT * FROM customers WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'customer not found' });
  const { name, phone, email, notes } = req.body;
  db.prepare('UPDATE customers SET name = ?, phone = ?, email = ?, notes = ? WHERE id = ?').run(
    name ?? existing.name,
    phone ?? existing.phone,
    email ?? existing.email,
    notes ?? existing.notes,
    req.params.id
  );
  res.json(db.prepare('SELECT * FROM customers WHERE id = ?').get(req.params.id));
});

// ---------- Requests (customer asks, business owner approves) ----------

app.post('/api/requests', (req, res) => {
  const { item_id, name, phone = '', email = '', note = '' } = req.body;
  if (!item_id) return res.status(400).json({ error: 'item_id is required' });
  if (!name || !name.trim()) return res.status(400).json({ error: 'name is required' });
  if (!phone.trim() && !email.trim()) return res.status(400).json({ error: 'phone or email is required' });

  const item = db.prepare('SELECT * FROM items WHERE id = ?').get(item_id);
  if (!item) return res.status(404).json({ error: 'item not found' });

  let customer = findCustomer(phone.trim(), email.trim());
  if (!customer) {
    const info = db.prepare('INSERT INTO customers (name, phone, email) VALUES (?, ?, ?)').run(
      name.trim(), phone.trim(), email.trim()
    );
    customer = db.prepare('SELECT * FROM customers WHERE id = ?').get(info.lastInsertRowid);
  }

  // Re-requesting an item already decided on reopens it as pending, so a
  // customer is never stuck with a stale decline they cannot ask about again.
  db.prepare(
    `INSERT INTO requests (item_id, customer_id, note) VALUES (?, ?, ?)
     ON CONFLICT(item_id, customer_id) DO UPDATE SET
       status = 'pending', note = excluded.note, created_at = datetime('now'), responded_at = NULL`
  ).run(item.id, customer.id, note.trim());

  res.status(201).json({ ok: true, customer_id: customer.id });
});

// A customer's own requests. Their id comes from the browser after they first
// ask for something -- enough to show status back to them, and it exposes only
// that one customer's rows.
app.get('/api/requests/mine/:customerId', (req, res) => {
  const rows = db.prepare(
    `SELECT r.id, r.status, r.created_at, r.responded_at, i.name AS item_name, i.status AS item_status
     FROM requests r JOIN items i ON i.id = r.item_id
     WHERE r.customer_id = ? ORDER BY r.created_at DESC`
  ).all(req.params.customerId);
  res.json(rows);
});

app.get('/api/requests', requireAdmin, (req, res) => {
  const { status } = req.query;
  const base =
    `SELECT r.id, r.status, r.note, r.created_at, r.responded_at,
            i.name AS item_name, i.status AS item_status,
            c.name AS customer_name, c.phone, c.email
     FROM requests r
     JOIN items i ON i.id = r.item_id
     JOIN customers c ON c.id = r.customer_id`;
  const rows = status
    ? db.prepare(`${base} WHERE r.status = ? ORDER BY r.created_at DESC`).all(status)
    : db.prepare(`${base} ORDER BY r.created_at DESC`).all();
  res.json(rows);
});

app.put('/api/requests/:id', requireAdmin, (req, res) => {
  const { status } = req.body;
  if (!['pending', 'approved', 'declined'].includes(status)) {
    return res.status(400).json({ error: 'status must be pending, approved or declined' });
  }
  const info = db.prepare(
    `UPDATE requests SET status = ?, responded_at = CASE WHEN ? = 'pending' THEN NULL ELSE datetime('now') END
     WHERE id = ?`
  ).run(status, status, req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: 'request not found' });
  res.json(db.prepare('SELECT * FROM requests WHERE id = ?').get(req.params.id));
});

// ---------- Shop settings ----------

app.get('/api/settings', (req, res) => {
  res.json(db.prepare('SELECT * FROM shop_settings WHERE id = 1').get());
});

app.put('/api/settings', requireAdmin, (req, res) => {
  const existing = db.prepare('SELECT * FROM shop_settings WHERE id = 1').get();
  const { shop_name, tagline, logo_url, accent_color, contact_phone, contact_email, address, hours_text } = req.body;
  db.prepare(
    `UPDATE shop_settings SET shop_name = ?, tagline = ?, logo_url = ?, accent_color = ?,
     contact_phone = ?, contact_email = ?, address = ?, hours_text = ? WHERE id = 1`
  ).run(
    (shop_name ?? existing.shop_name).trim() || existing.shop_name,
    tagline ?? existing.tagline,
    logo_url ?? existing.logo_url,
    accent_color ?? existing.accent_color,
    contact_phone ?? existing.contact_phone,
    contact_email ?? existing.contact_email,
    address ?? existing.address,
    hours_text ?? existing.hours_text
  );
  res.json(db.prepare('SELECT * FROM shop_settings WHERE id = 1').get());
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Shop CRM running at http://localhost:${PORT}`));
