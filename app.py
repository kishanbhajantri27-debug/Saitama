import os
import re
import secrets
from functools import wraps

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

import db  # noqa: E402
from mailer import send_decision  # noqa: E402

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme123")
if not os.environ.get("ADMIN_PASS"):
    print(
        "[shop-crm] ADMIN_PASS not set - using default admin login "
        "(admin / changeme123). Set ADMIN_USER/ADMIN_PASS in .env before "
        "sharing this publicly."
    , flush=True)

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

db.init()
app = Flask(__name__, static_folder=None)


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        # compare_digest keeps the check constant-time so a wrong password
        # cannot be narrowed down by timing it.
        if (
            auth
            and auth.type == "basic"
            and secrets.compare_digest(auth.username or "", ADMIN_USER)
            and secrets.compare_digest(auth.password or "", ADMIN_PASS)
        ):
            return view(*args, **kwargs)
        return (
            "Authentication required",
            401,
            {"WWW-Authenticate": 'Basic realm="Shop Admin"'},
        )

    return wrapped


def find_customer(phone, email):
    if phone:
        row = db.query_one("SELECT * FROM customers WHERE phone = ? AND phone != ''", (phone,))
        if row:
            return row
    if email:
        row = db.query_one("SELECT * FROM customers WHERE email = ? AND email != ''", (email,))
        if row:
            return row
    return None


# ---------- Static files ----------

@app.get("/admin.html")
@require_admin
def admin_page():
    return send_from_directory(PUBLIC_DIR, "admin.html")


@app.get("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(PUBLIC_DIR, filename)


# ---------- Items ----------

@app.get("/api/items")
def list_items():
    status = request.args.get("status")
    if status:
        return jsonify(db.query(
            "SELECT * FROM items WHERE status = ? ORDER BY created_at DESC", (status,)))
    return jsonify(db.query("SELECT * FROM items ORDER BY created_at DESC"))


@app.post("/api/items")
@require_admin
def create_item():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    status = body.get("status", "available")
    if not name:
        return jsonify(error="name is required"), 400
    if status not in ("available", "upcoming"):
        return jsonify(error="invalid status"), 400

    try:
        price = float(body.get("price") or 0)
    except (TypeError, ValueError):
        price = 0

    _, new_id = db.execute(
        """INSERT INTO items (name, description, price, category, image_url, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, body.get("description", ""), price, body.get("category", ""),
         body.get("image_url", ""), status),
    )
    return jsonify(db.query_one("SELECT * FROM items WHERE id = ?", (new_id,))), 201


@app.put("/api/items/<int:item_id>")
@require_admin
def update_item(item_id):
    existing = db.query_one("SELECT * FROM items WHERE id = ?", (item_id,))
    if not existing:
        return jsonify(error="item not found"), 404

    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if status is not None and status not in ("available", "upcoming"):
        return jsonify(error="invalid status"), 400

    price = existing["price"]
    if body.get("price") is not None:
        try:
            price = float(body["price"])
        except (TypeError, ValueError):
            pass

    db.execute(
        """UPDATE items SET name = ?, description = ?, price = ?, category = ?,
           image_url = ?, status = ? WHERE id = ?""",
        (
            body.get("name", existing["name"]),
            body.get("description", existing["description"]),
            price,
            body.get("category", existing["category"]),
            body.get("image_url", existing["image_url"]),
            status or existing["status"],
            item_id,
        ),
    )
    return jsonify(db.query_one("SELECT * FROM items WHERE id = ?", (item_id,)))


@app.delete("/api/items/<int:item_id>")
@require_admin
def delete_item(item_id):
    changes, _ = db.execute("DELETE FROM items WHERE id = ?", (item_id,))
    if changes == 0:
        return jsonify(error="item not found"), 404
    return "", 204


# ---------- Requests ----------

# Pending counts for every item in one query, so the admin table does not fire
# a separate request per row.
@app.get("/api/requests/counts")
@require_admin
def request_counts():
    rows = db.query(
        "SELECT item_id, COUNT(*) AS count FROM requests WHERE status = 'pending' GROUP BY item_id")
    return jsonify({str(r["item_id"]): r["count"] for r in rows})


@app.get("/api/items/<int:item_id>/requests")
@require_admin
def item_requests(item_id):
    return jsonify(db.query(
        """SELECT c.id, c.name, c.phone, c.email, r.status, r.created_at
           FROM requests r JOIN customers c ON c.id = r.customer_id
           WHERE r.item_id = ? ORDER BY r.created_at ASC""",
        (item_id,),
    ))


@app.post("/api/requests")
def create_request():
    body = request.get_json(silent=True) or {}
    item_id = body.get("item_id")
    name = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    email = (body.get("email") or "").strip()
    note = (body.get("note") or "").strip()

    if not item_id:
        return jsonify(error="item_id is required"), 400
    if not name:
        return jsonify(error="name is required"), 400
    # Email carries the decision back to the customer, so it is the one contact
    # detail a request cannot do without.
    if not email:
        return jsonify(error="email is required"), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="that email does not look right"), 400

    item = db.query_one("SELECT * FROM items WHERE id = ?", (item_id,))
    if not item:
        return jsonify(error="item not found"), 404

    customer = find_customer(phone, email)
    if not customer:
        _, customer_id = db.execute(
            "INSERT INTO customers (name, phone, email) VALUES (?, ?, ?)", (name, phone, email))
    else:
        customer_id = customer["id"]

    # Re-requesting an item already decided on reopens it as pending, so a
    # customer is never stuck with a stale decline they cannot ask about again.
    db.execute(
        """INSERT INTO requests (item_id, customer_id, note) VALUES (?, ?, ?)
           ON CONFLICT(item_id, customer_id) DO UPDATE SET
             status = 'pending', note = excluded.note,
             created_at = datetime('now'), responded_at = NULL, seen_at = NULL""",
        (item["id"], customer_id, note),
    )
    return jsonify(ok=True, customer_id=customer_id), 201


# A customer's own requests. Their id comes from the browser after they first
# ask for something -- enough to show status back to them, and it exposes only
# that one customer's rows.
@app.get("/api/requests/mine/<int:customer_id>")
def my_requests(customer_id):
    return jsonify(db.query(
        """SELECT r.id, r.status, r.created_at, r.responded_at, r.seen_at,
                  i.name AS item_name, i.status AS item_status
           FROM requests r JOIN items i ON i.id = r.item_id
           WHERE r.customer_id = ? ORDER BY r.created_at DESC""",
        (customer_id,),
    ))


# Called once the customer has been shown their decisions, so the same
# approval is not announced on every visit.
@app.post("/api/requests/mine/<int:customer_id>/seen")
def mark_seen(customer_id):
    changes, _ = db.execute(
        """UPDATE requests SET seen_at = datetime('now')
           WHERE customer_id = ? AND status != 'pending' AND seen_at IS NULL""",
        (customer_id,),
    )
    return jsonify(ok=True, marked=changes)


@app.get("/api/requests")
@require_admin
def list_requests():
    base = """SELECT r.id, r.status, r.note, r.created_at, r.responded_at,
                     r.item_id, r.customer_id,
                     i.name AS item_name, i.status AS item_status,
                     c.name AS customer_name, c.phone, c.email
              FROM requests r
              JOIN items i ON i.id = r.item_id
              JOIN customers c ON c.id = r.customer_id"""
    status = request.args.get("status")
    if status:
        return jsonify(db.query(f"{base} WHERE r.status = ? ORDER BY r.created_at DESC", (status,)))
    return jsonify(db.query(f"{base} ORDER BY r.created_at DESC"))


@app.put("/api/requests/<int:request_id>")
@require_admin
def decide_request(request_id):
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if status not in ("pending", "approved", "declined"):
        return jsonify(error="status must be pending, approved or declined"), 400

    # seen_at resets so a changed decision is announced again rather than
    # inheriting the acknowledgement of the previous one.
    changes, _ = db.execute(
        """UPDATE requests SET status = ?,
             responded_at = CASE WHEN ? = 'pending' THEN NULL ELSE datetime('now') END,
             seen_at = NULL
           WHERE id = ?""",
        (status, status, request_id),
    )
    if changes == 0:
        return jsonify(error="request not found"), 404

    if status != "pending":
        detail = db.query_one(
            """SELECT c.name AS customer_name, c.email, i.name AS item_name
               FROM requests r JOIN customers c ON c.id = r.customer_id
               JOIN items i ON i.id = r.item_id WHERE r.id = ?""",
            (request_id,),
        )
        shop_name = db.query_one("SELECT shop_name FROM shop_settings WHERE id = 1")["shop_name"]
        send_decision(detail["email"], shop_name, detail["customer_name"],
                      detail["item_name"], status)

    return jsonify(db.query_one("SELECT * FROM requests WHERE id = ?", (request_id,)))


# ---------- Purchases ----------

@app.post("/api/purchases")
@require_admin
def record_purchase():
    body = request.get_json(silent=True) or {}
    customer_id = body.get("customer_id")
    item_id = body.get("item_id")

    customer = db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    if not customer:
        return jsonify(error="customer not found"), 404
    item = db.query_one("SELECT * FROM items WHERE id = ?", (item_id,))
    if not item:
        return jsonify(error="item not found"), 404

    # Checked against None rather than falsiness: `or 1` would quietly turn a
    # quantity of 0 into 1 instead of rejecting it.
    raw_quantity = body.get("quantity")
    try:
        quantity = 1 if raw_quantity is None else int(raw_quantity)
    except (TypeError, ValueError):
        return jsonify(error="quantity must be a whole number"), 400
    if quantity < 1:
        return jsonify(error="quantity must be at least 1"), 400

    # Price defaults to what the item costs today, but stays overridable for a
    # discount. Either way it is frozen here rather than read back later.
    price = item["price"]
    if body.get("price") is not None:
        try:
            price = float(body["price"])
        except (TypeError, ValueError):
            return jsonify(error="price must be a number"), 400

    _, new_id = db.execute(
        """INSERT INTO purchases (customer_id, item_id, item_name, price, quantity, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (customer["id"], item["id"], item["name"], price, quantity,
         (body.get("note") or "").strip()),
    )
    return jsonify(db.query_one("SELECT * FROM purchases WHERE id = ?", (new_id,))), 201


@app.get("/api/purchases")
@require_admin
def list_purchases():
    base = """SELECT p.*, c.name AS customer_name, c.email, c.phone
              FROM purchases p JOIN customers c ON c.id = p.customer_id"""
    customer_id = request.args.get("customer_id")
    if customer_id:
        return jsonify(db.query(
            f"{base} WHERE p.customer_id = ? ORDER BY p.bought_at DESC", (customer_id,)))
    return jsonify(db.query(f"{base} ORDER BY p.bought_at DESC"))


@app.get("/api/purchases/mine/<int:customer_id>")
def my_purchases(customer_id):
    return jsonify(db.query(
        """SELECT id, item_name, price, quantity, bought_at
           FROM purchases WHERE customer_id = ? ORDER BY bought_at DESC""",
        (customer_id,),
    ))


@app.delete("/api/purchases/<int:purchase_id>")
@require_admin
def delete_purchase(purchase_id):
    changes, _ = db.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
    if changes == 0:
        return jsonify(error="purchase not found"), 404
    return "", 204


# ---------- Customers ----------

@app.get("/api/customers")
@require_admin
def list_customers():
    return jsonify(db.query(
        """SELECT c.*, GROUP_CONCAT(i.name, ', ') AS interests
           FROM customers c
           LEFT JOIN requests r ON r.customer_id = c.id
           LEFT JOIN items i ON i.id = r.item_id
           GROUP BY c.id
           ORDER BY c.created_at DESC"""
    ))


@app.put("/api/customers/<int:customer_id>")
@require_admin
def update_customer(customer_id):
    existing = db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    if not existing:
        return jsonify(error="customer not found"), 404
    body = request.get_json(silent=True) or {}
    db.execute(
        "UPDATE customers SET name = ?, phone = ?, email = ?, notes = ? WHERE id = ?",
        (
            body.get("name", existing["name"]),
            body.get("phone", existing["phone"]),
            body.get("email", existing["email"]),
            body.get("notes", existing["notes"]),
            customer_id,
        ),
    )
    return jsonify(db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,)))


# ---------- Shop settings ----------

@app.get("/api/settings")
def get_settings():
    return jsonify(db.query_one("SELECT * FROM shop_settings WHERE id = 1"))


@app.put("/api/settings")
@require_admin
def update_settings():
    existing = db.query_one("SELECT * FROM shop_settings WHERE id = 1")
    body = request.get_json(silent=True) or {}
    shop_name = (body.get("shop_name") or existing["shop_name"]).strip() or existing["shop_name"]
    db.execute(
        """UPDATE shop_settings SET shop_name = ?, tagline = ?, logo_url = ?, accent_color = ?,
           contact_phone = ?, contact_email = ?, address = ?, hours_text = ? WHERE id = 1""",
        (
            shop_name,
            body.get("tagline", existing["tagline"]),
            body.get("logo_url", existing["logo_url"]),
            body.get("accent_color", existing["accent_color"]),
            body.get("contact_phone", existing["contact_phone"]),
            body.get("contact_email", existing["contact_email"]),
            body.get("address", existing["address"]),
            body.get("hours_text", existing["hours_text"]),
        ),
    )
    return jsonify(db.query_one("SELECT * FROM shop_settings WHERE id = 1"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or 3000)
    print(f"Shop CRM running at http://localhost:{port}", flush=True)
    app.run(host="127.0.0.1", port=port, threaded=True)
