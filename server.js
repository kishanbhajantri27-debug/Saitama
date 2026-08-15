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

app.get('/api/items/:id/waitlist', requireAdmin, (req, res) => {
  const rows = db.prepare(
    `SELECT c.id, c.name, c.phone, c.email, w.created_at
     FROM waitlist w JOIN customers c ON c.id = w.customer_id
     WHERE w.item_id = ? ORDER BY w.created_at ASC`
  ).all(req.params.id);
  res.json(rows);
});

// ---------- Customers ----------

app.get('/api/customers', requireAdmin, (req, res) => {
  const rows = db.prepare('SELECT * FROM customers ORDER BY created_at DESC').all();
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

// ---------- Waitlist (notify me for upcoming items) ----------

app.post('/api/waitlist', (req, res) => {
  const { item_id, name, phone = '', email = '' } = req.body;
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

  db.prepare('INSERT OR IGNORE INTO waitlist (item_id, customer_id) VALUES (?, ?)').run(item.id, customer.id);
  res.status(201).json({ ok: true, customer_id: customer.id });
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
