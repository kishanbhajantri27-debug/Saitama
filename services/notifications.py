"""Back-in-stock requests and the notices they produce.

Delivery is deliberately shallow: a row is written and, if SMTP happens to be
configured, an email goes out. No SMS, no push -- those are the parent
platform's job (spec section 22).
"""
import config
import db
from services import catalog

try:
    from mailer import send_decision  # reused from the previous app
except Exception:  # pragma: no cover - mail is optional
    send_decision = None


def request_notify(customer_id, variant_id):
    variant = catalog.get_variant(variant_id)
    if not variant:
        raise ValueError("product not found")

    existing = db.query_one(
        """SELECT * FROM notifications
           WHERE customer_id = ? AND variant_id = ? AND kind = 'back_in_stock'
             AND fired_at IS NULL""",
        (customer_id, variant_id),
    )
    if existing:
        return existing

    _, new_id = db.execute(
        """INSERT INTO notifications (store_id, customer_id, variant_id, kind, title, body)
           VALUES (?, ?, ?, 'back_in_stock', ?, ?)""",
        (config.STORE_ID, customer_id, variant_id,
         f"We will tell you when {variant['product_name']} is back",
         f"{variant['product_name']} ({variant['label']}) is out of stock right now."),
    )
    return db.query_one("SELECT * FROM notifications WHERE id = ?", (new_id,))


def for_customer(customer_id, unseen_only=False):
    sql = """SELECT n.*, v.label AS variant_label, p.name AS product_name, p.image_url
             FROM notifications n
             LEFT JOIN product_variants v ON v.id = n.variant_id
             LEFT JOIN products p ON p.id = v.product_id
             WHERE n.customer_id = ? AND n.fired_at IS NOT NULL"""
    if unseen_only:
        sql += " AND n.seen_at IS NULL"
    sql += " ORDER BY n.fired_at DESC"
    return db.query(sql, (customer_id,))


def pending_watch_count(variant_id):
    row = db.query_one(
        """SELECT COUNT(*) AS n FROM notifications
           WHERE variant_id = ? AND kind = 'back_in_stock' AND fired_at IS NULL""",
        (variant_id,),
    )
    return row["n"] if row else 0


def fire_back_in_stock(variant_id):
    """Called after stock arrives: wake everyone waiting on this variant."""
    variant = catalog.get_variant(variant_id)
    if not variant or variant["stock"]["available"] <= 0:
        return 0

    waiting = db.query(
        """SELECT n.*, c.name AS customer_name, c.email
           FROM notifications n JOIN customers c ON c.id = n.customer_id
           WHERE n.variant_id = ? AND n.kind = 'back_in_stock' AND n.fired_at IS NULL""",
        (variant_id,),
    )
    for row in waiting:
        db.execute(
            """UPDATE notifications
               SET fired_at = datetime('now'), title = ?, body = ?, seen_at = NULL
               WHERE id = ?""",
            (f"{variant['product_name']} is back in stock",
             f"{variant['product_name']} ({variant['label']}) is available again.",
             row["id"]),
        )
        if send_decision and row.get("email"):
            try:
                send_decision(row["email"], "the store", row["customer_name"],
                              variant["product_name"], "approved")
            except Exception:
                pass  # mail must never break a stock update
    return len(waiting)


def mark_seen(customer_id):
    changes, _ = db.execute(
        """UPDATE notifications SET seen_at = datetime('now')
           WHERE customer_id = ? AND fired_at IS NOT NULL AND seen_at IS NULL""",
        (customer_id,),
    )
    return changes
