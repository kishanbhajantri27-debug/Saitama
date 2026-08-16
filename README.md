# Store Showcase

A demo-quality child app for a store-management platform. It runs one retail store; the parent platform will eventually run many, so every store-scoped record here already carries a `store_id`.

The whole app exists to make one flow feel real:

> search → see live stock → reserve → store accepts → ready for pickup → scan the code → collect → inventory and dashboard move

Two modes, no account needed for either:

- **Customer** — browse, search, filter, product detail with live availability and stock freshness, reserve with a QR code, track the reservation, wishlist, back-in-stock alerts, multi-item availability check, store info.
- **Store** — dashboard, inventory with add/remove/adjust, reservation queue (accept, ready, reject, complete), barcode scanner, sales and inventory analytics.

## Running it

```bash
pip install -r requirements.txt
python app.py
```

Open <http://localhost:3000>. Store mode has three demo roles — owner, manager and staff — each one tap from the sign-in screen, so nothing needs typing.

## Staff accounts and roles

Store mode runs on real accounts with roles (`owner`, `manager`, `staff`), salted scrypt passwords, and an active/disabled state.

**Authorization is enforced in the services, not just the routes.** Hiding a button is a courtesy; refusing the operation is the control. Both layers check, and the test suite fails if either is removed.

The full matrix lives in one place, `services/security.py`, and is served at `GET /api/permissions`. Broadly: staff do counter work (stock moves, accepting and completing reservations); managers add stock-takes, rejections, analytics and the audit log; owners add staff administration, settings, voids and the demo reset.

**No passwords are committed.** Seeding generates a strong random one per account. You never need them for the demo — the role buttons ask the server for a session instead — but you can pin them with `DEMO_OWNER_PASSWORD`, `DEMO_MANAGER_PASSWORD`, `DEMO_STAFF_PASSWORD`.

### Turning off demo mode

Those one-tap buttons are an authentication bypass, gated on `DEMO_MODE`:

```bash
DEMO_MODE=false python app.py
```

With it off the endpoint returns 404 and password sign-in is the only way in. Since the seeded passwords are random and printed once at seed time, a fresh database with demo mode off has **no known credentials** — set one deliberately with `DEMO_OWNER_PASSWORD` before seeding. Locked out by default is the right posture for anything leaving demo.

Every meaningful action, and every refused attempt, lands in an audit log readable by managers and owners at `/store/audit`.

## Tests

```bash
python -m pytest tests/ -q
```

196 tests covering the permission matrix, unauthorized access over HTTP, role changes, disabled and deleted accounts, audit completeness and secret redaction, plus regressions pinning the stock arithmetic, reservation lifecycle and search.

Demo data seeds itself on first boot: 8 products, 18 variants with SKUs and barcodes, stock at varied ages, customers, live reservations and a week of past sales. Delete `data/store.db` to start over.

Optional `.env` (see `.env.example`): `STAFF_PASSCODE`, `PORT`, `STORE_ID`, `RESERVATION_MINUTES`, and SMTP settings for back-in-stock emails.

## Layout

```
app.py            Flask factory + static shell
config.py         store/tenant id, freshness and reservation thresholds
db.py             schema, connections, transactions
seed.py           demo data (idempotent)
services/         all business logic — no Flask imports here
api/              HTTP routes + staff auth — no business rules here
public/js/api.js  the one place that talks to the backend
public/js/views/  one module per screen
```

**The split matters.** Services never import Flask, and routes never contain rules. On the client, only `api.js` calls `fetch`. When the parent platform's real API arrives, `api.js` and the service internals change; the screens do not.

## How stock actually works

- `inventory` holds `on_hand` and `reserved` per variant per branch. **Available = on_hand − reserved.**
- **A reservation holds stock immediately**, not when staff accept it. Otherwise two customers could reserve the last unit. Completing a pickup is what finally removes it from `on_hand`.
- Rejecting, cancelling or expiring a reservation releases the hold.
- Every change writes to `inventory_movements`, which is append-only — the dashboard reads from those events rather than from a running total, so any number can be traced to what caused it.
- **Freshness travels with every count.** A quantity is only as good as when it was taken, so the age is shown everywhere and anything older than 3 hours is flagged as possibly outdated.

## Barcode scanning

Real detection uses `BarcodeDetector`, which currently ships on Chrome for Android and little else. Where it is missing the camera still previews and the manual SKU/barcode field is the working path, plus demo buttons so the showcase never depends on hardware.

**Only the fallback path has been verified here** — this development browser has no `BarcodeDetector`. Test the camera on an Android phone before demoing that specific step.

## Deliberately mocked

Payments, invoices and GST are rows, not integrations. No SMS, no subscription billing, no AI, no real customer data. The tables exist so the shape is right when the real thing replaces them.

## Working on this together

- `main` — always working; merge into it rather than committing directly.
- `parent-app` — owner-side work.
- `student-app` — customer-side work.

Split by file to keep merges cheap: owner screens in `public/js/views/store.js`, customer screens in `public/js/views/customer.js`. `app.py`, `db.py`, `services/` and `public/css/app.css` are shared — say so before changing them.

`db.py` is the sharpest edge: two people adding columns to the same table conflict every time, and a half-applied schema change breaks the other person's database, not just their merge. Agree on schema changes before writing them.

The database lives in `data/` and is gitignored. A fresh clone seeds its own — never commit the `.db` file.
