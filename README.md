# Store Showcase

A demo-quality child app for a store-management platform. It runs one retail store; the parent platform will eventually run many, so every store-scoped record here already carries a `store_id`.

The whole app exists to make one flow feel real:

> search → see live stock → reserve → store accepts → ready for pickup → scan the code → collect → inventory and dashboard move

Two modes, no account needed for either:

- **Customer** — browse, search, filter, product detail with live availability and stock freshness, reserve with a QR code, track the reservation, wishlist, back-in-stock alerts, multi-item availability check, store info.
- **Store** — dashboard, inventory with add/remove/adjust, reservation queue (accept, ready, reject, complete), barcode scanner, sales and inventory analytics, shop settings.

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

### Login rate limiting

Failed sign-ins are counted on a sliding window, per username (5 in 15 minutes) and per client address (20 in 15 minutes). Tripping either returns `429` with a `Retry-After`. A correct password clears that username's counter, so an ordinary typo or two costs nothing.

Three details that matter more than the numbers:

- **Unknown usernames are limited exactly like real ones.** Limiting only real accounts would turn the lockout into an oracle for which usernames exist.
- **A locked account still refuses the correct password** until the window passes, or the limit would be bypassable by simply continuing to guess.
- **`X-Forwarded-For` is ignored unless `TRUST_PROXY=true`.** Clients can set that header themselves, so honouring it without a proxy in front would let anyone invent a fresh address per request.

Counters live in memory alongside sessions: a restart forgives everyone, and multiple worker processes would each keep their own tally. Both need a shared store before this runs anywhere real.

## Shop types

The customer showcase is not one fixed layout — `stores.type` picks it, and an owner or manager changes it from **Store → Settings**:

- **General** (default) — the flat curated homepage this app started with: Popular, Available now, Recommended.
- **Grocery** — the catalogue grouped into aisles by category, availability surfaced up top.
- **Mall** — the catalogue grouped into wings by brand, framed as a directory of shops.

All three read the same `products`/`inventory` tables; only `public/js/views/customer.js`'s `homeView` dispatch and `public/js/app.js`'s landing logo change per type. Adding a fourth type means adding an entry to `TYPE_INFO` (client) and `SHOWCASE_TYPES` (`services/store.py`) plus a `*Body()` renderer — the settings screen, validation and audit trail need no changes. Changing the type is `settings.edit` (owner-only); viewing the settings screen is `settings.view` (owner and manager).

## Installing as an app

The showcase is an installable PWA: `public/manifest.webmanifest` and `public/sw.js` (registered from `app.js`) let a phone "Add to Home Screen" it and open it full-screen, no browser chrome. The service worker only ever caches the static shell (HTML/CSS/JS/icons) with a stale-while-revalidate strategy — it never touches anything under `/api/`, so stock and reservations are never served stale from a cache. On Chrome/Android, `beforeinstallprompt` is captured and surfaced as an "Install app" button on the landing screen; iOS has no such event, so installing there is the manual share-sheet "Add to Home Screen" (the `apple-touch-icon` and `apple-mobile-web-app-*` meta tags in `index.html` are for that path).

## The parent platform integration

This store can be paired with a parent platform (ShopCRM's head office is the
one in production use, but anything speaking the same two endpoints works):
the parent **pushes its catalogue** down and **pulls stock levels** back for
chain-wide reporting. This store keeps owning everything else — inventory
counts, reservations, staff, customers, orders — the parent never touches
`on_hand` directly; the only path that ever changes it is
`inventory.change_stock`, called locally, the same as any other goods-in.

A different trust boundary from the rest of the API: the caller is head
office's own software, not a person, authenticated by `X-Parent-Token`
against `PARENT_TOKEN` rather than a staff session. Unset by default — the
two endpoints answer `404` until it is configured, the same posture
`DEMO_MODE` takes when off.

```bash
POST /api/parent/catalog   # { store_id?, products: [{parent_ref, name, ..., variants: [{parent_ref, sku, price, ...}]}] }
GET  /api/parent/inventory?branch_id=...
```

Products and variants are matched by `parent_ref` — the parent's own id for
each row — never by name or SKU, both of which a shopkeeper can legitimately
rename here. A push with no `parent_ref` on an item is refused outright, and
the whole push is one transaction: a malformed item partway through a large
payload must not leave the catalogue half updated.

See `services/parent_sync.py` for the write/read logic and
`api/routes.py`'s "Parent platform integration" section for the routes.

## Adding and editing the catalogue locally

Owners and managers can also add or edit a product straight from the
Inventory screen — the **+ Add** button in its header, or **Edit** on any
row. Before this there was no write path for a product at all: `product.
create`/`product.edit` had been in the permission matrix from the start, but
nothing implemented them, so the only way one ever existed was `seed.py` or a
push from the parent platform. Product and its one variant are saved
together in the same form, matching how this app already has no screen that
edits them apart. A variant's SKU is checked for a collision before saving,
and deleting a product's last variant is refused — delete the product
instead, since a product with no variant left is a shelf label nothing can
ever sell.

The same form takes a **photo** — a real file picker, not a pasted URL. There
is no upload endpoint or file storage anywhere in this app, so a photo is
read client-side with `FileReader` and saved as a `data:` URL in the existing
`image_url` column: a string that happens to decode to a picture, which
needed nothing new on the server. Capped at 1.5 MB client-side, since nothing
else bounds how large that string can get. Saving without touching the photo
leaves it as it was; the **Remove** button clears it explicitly — those are
deliberately different things, so an ordinary rename can never silently wipe
the picture.

## Tests

```bash
python -m pytest tests/ -q
```

274 tests covering the permission matrix, unauthorized access over HTTP, role changes, disabled and deleted accounts, audit completeness, secret redaction, login rate limiting, the parent-platform catalogue push/inventory pull and its isolation from staff sessions, local product/variant create and edit (including photo save/keep/clear semantics), plus regressions pinning the stock arithmetic, reservation lifecycle and search, and the hold allowance -- what spends it, what deliberately does not, the three-days-running warning and the pass that extends a day.

Demo data seeds itself on first boot: 8 products, 18 variants with SKUs and barcodes, stock at varied ages, customers, live reservations and a week of past sales. Delete `data/store.db` to start over.

Optional `.env` (see `.env.example`): `PORT`, `STORE_ID`, `RESERVATION_MINUTES`, `DEMO_MODE`, `TRUST_PROXY`, `DEMO_*_PASSWORD`, and SMTP settings for back-in-stock emails.

Hold fair-use is tunable the same way: `HOLD_TYPES_PER_DAY`, `HOLD_REPEAT_STREAK_DAYS`, `HOLD_PASS_EXTRA_TYPES`, `HOLD_PASS_PRICE`, and `HOLD_PASS_QR_PAYLOAD` — any payment string; setting it replaces the built-in placeholder QR and drops its DEMO label. Keep a real one in `.env`, never in `config.py`: `.env` is gitignored and a payment handle is not something to commit.

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
public/manifest.webmanifest, public/sw.js, public/icons/   installable-app plumbing
```

**The split matters.** Services never import Flask, and routes never contain rules. On the client, only `api.js` calls `fetch`. When the parent platform's real API arrives, `api.js` and the service internals change; the screens do not.

## How stock actually works

- `inventory` holds `on_hand` and `reserved` per variant per branch. **Available = on_hand − reserved.**
- **A reservation holds stock immediately**, not when staff accept it. Otherwise two customers could reserve the last unit. Completing a pickup is what finally removes it from `on_hand`.
- Rejecting, cancelling or expiring a reservation releases the hold.
- **Holds are rationed: five product types per shopper per day** (`services/holds.py`). A hold costs the shopper nothing but takes a unit off the shelf for an hour, so the allowance is spent on *distinct types* — re-holding the same item is free, quantity is not counted, and cancelling does not refund the slot (or the cap would be avoidable by holding and cancelling in a loop). Usage is counted from `reservations` rather than kept as a total, so it cannot drift from its own history. Enforced at the route, not in `reservations.create()`: it is a shopfront policy, and staff placing a hold at the counter are not rationed by it.
- Filling the allowance **three days running** warns the shopper that charges may apply. A live streak, not a tally over a window — one quiet day ends it. Running out offers a payment QR (`HOLD_PASS_QR_PAYLOAD`) that grants one more allowance for the day; nothing verifies the payment, so the button under it stands in for a gateway webhook calling `holds.grant_pass()`.
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
