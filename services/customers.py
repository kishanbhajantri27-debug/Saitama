"""Customers and their wishlists."""
import config
import db
from services import catalog


def get(customer_id):
    return db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))


def list_all():
    return db.query(
        "SELECT * FROM customers WHERE store_id = ? ORDER BY created_at DESC", (config.STORE_ID,))


def find_or_create(name, phone="", email=""):
    name = (name or "").strip() or "Guest"
    phone, email = (phone or "").strip(), (email or "").strip()
    if phone:
        row = db.query_one(
            "SELECT * FROM customers WHERE phone = ? AND phone != ''", (phone,))
        if row:
            return row
    if email:
        row = db.query_one(
            "SELECT * FROM customers WHERE email = ? AND email != ''", (email,))
        if row:
            return row
    _, new_id = db.execute(
        "INSERT INTO customers (store_id, name, phone, email) VALUES (?, ?, ?, ?)",
        (config.STORE_ID, name, phone, email),
    )
    return get(new_id)


DEMO_EMAIL = "demo@example.com"


def demo_customer():
    """The identity customer mode browses as, so the demo needs no signup.

    Pinned to the seeded demo shopper rather than "first customer by id" --
    otherwise the wishlist and notifications seeded for them belong to somebody
    the visitor is not.
    """
    row = db.query_one(
        "SELECT * FROM customers WHERE store_id = ? AND email = ?",
        (config.STORE_ID, DEMO_EMAIL),
    )
    return row or find_or_create("Demo Shopper", email=DEMO_EMAIL)


def wishlist(customer_id, branch_id=None):
    """Saved products, each carrying live stock so 'back in stock' can show."""
    rows = db.query(
        """SELECT w.id AS wishlist_id, w.created_at, p.id AS product_id
           FROM wishlists w JOIN products p ON p.id = w.product_id
           WHERE w.customer_id = ? ORDER BY w.created_at DESC""",
        (customer_id,),
    )
    out = []
    for row in rows:
        product = catalog.get_product(row["product_id"], branch_id)
        if not product:
            continue
        product["wishlist_id"] = row["wishlist_id"]
        product["saved_at"] = row["created_at"]
        product["back_in_stock"] = product["available"] > 0
        out.append(product)
    return out


def add_to_wishlist(customer_id, product_id):
    db.execute(
        """INSERT OR IGNORE INTO wishlists (store_id, customer_id, product_id)
           VALUES (?, ?, ?)""",
        (config.STORE_ID, customer_id, product_id),
    )
    return wishlist(customer_id)


def remove_from_wishlist(customer_id, product_id):
    db.execute(
        "DELETE FROM wishlists WHERE customer_id = ? AND product_id = ?",
        (customer_id, product_id),
    )
    return wishlist(customer_id)


def wishlist_product_ids(customer_id):
    return [
        r["product_id"]
        for r in db.query("SELECT product_id FROM wishlists WHERE customer_id = ?", (customer_id,))
    ]
