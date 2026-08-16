"""Reservation lifecycle and its effect on stock.

Stock is held the moment a customer reserves, not when staff accept. The spec's
walkthrough is explicit about it -- 4 on hand, customer reserves one, available
reads 3 straight away -- and it is the only safe reading: if the hold waited
for staff, two customers could both reserve the last unit.

    pending --accept--> accepted --ready--> ready_for_pickup --complete--> completed
       |                    |                  |
       +---- reject/cancel/expire -------------+  (releases the hold)
"""
import random
from datetime import datetime, timedelta, timezone

import config
import db
from services import inventory

OPEN_STATES = ("pending", "accepted", "ready_for_pickup")


class ReservationError(Exception):
    """Something the caller did wrong: surfaces as a 400, not a 500."""


def _code():
    return f"RSV-{random.randint(10000, 99999)}"


def _expiry(minutes=None):
    minutes = minutes or config.RESERVATION_MINUTES
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _hydrate(row):
    if not row:
        return None
    row["expires_in_minutes"] = _minutes_left(row.get("expires_at"))
    row["is_open"] = row["status"] in OPEN_STATES
    return row


def _minutes_left(expires_at):
    if not expires_at:
        return None
    try:
        end = datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, round((end - datetime.now(timezone.utc)).total_seconds() / 60))


DETAIL_SQL = """
SELECT r.*, v.sku, v.label AS variant_label, v.price, v.barcode,
       p.id AS product_id, p.name AS product_name, p.brand, p.image_url,
       c.name AS customer_name, c.phone, c.email
FROM reservations r
JOIN product_variants v ON v.id = r.variant_id
JOIN products p ON p.id = v.product_id
JOIN customers c ON c.id = r.customer_id
"""


def get(reservation_id):
    return _hydrate(db.query_one(f"{DETAIL_SQL} WHERE r.id = ?", (reservation_id,)))


def get_by_code(code):
    return _hydrate(db.query_one(f"{DETAIL_SQL} WHERE r.code = ?", ((code or "").strip().upper(),)))


def list_all(status=None, customer_id=None):
    expire_due()
    sql, params = DETAIL_SQL, []
    clauses = []
    if status and status != "all":
        if status == "open":
            clauses.append(f"r.status IN ({','.join('?' * len(OPEN_STATES))})")
            params += list(OPEN_STATES)
        else:
            clauses.append("r.status = ?")
            params.append(status)
    if customer_id:
        clauses.append("r.customer_id = ?")
        params.append(customer_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY r.created_at DESC, r.id DESC"
    return [_hydrate(r) for r in db.query(sql, tuple(params))]


def create(variant_id, customer_id, quantity=1, note="", minutes=None, branch_id=None):
    """Place a hold. Fails if the stock is not actually there."""
    branch_id = branch_id or config.BRANCH_ID
    quantity = int(quantity)
    if quantity < 1:
        raise ReservationError("quantity must be at least 1")

    expire_due()

    with db.transaction() as conn:
        variant = conn.execute(
            "SELECT * FROM product_variants WHERE id = ?", (variant_id,)).fetchone()
        if not variant:
            raise ReservationError("product not found")
        customer = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not customer:
            raise ReservationError("customer not found")

        inventory.ensure_row(conn, variant_id, branch_id)
        stock = conn.execute(
            "SELECT * FROM inventory WHERE variant_id = ? AND branch_id = ?",
            (variant_id, branch_id),
        ).fetchone()

        available = stock["on_hand"] - stock["reserved"]
        if quantity > available:
            raise ReservationError(
                f"only {available} available" if available else "out of stock")

        # Hold it now. Read inside the same transaction as the write so two
        # customers cannot both claim the last unit.
        conn.execute(
            "UPDATE inventory SET reserved = reserved + ? WHERE id = ?", (quantity, stock["id"]))

        code = _code()
        while conn.execute("SELECT 1 FROM reservations WHERE code = ?", (code,)).fetchone():
            code = _code()

        cur = conn.execute(
            """INSERT INTO reservations
                 (code, store_id, branch_id, variant_id, customer_id, quantity, note, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, config.STORE_ID, branch_id, variant_id, customer_id,
             quantity, note, _expiry(minutes)),
        )
        new_id = cur.lastrowid

        # Logged after the insert so the timeline can name the reservation.
        inventory.record_movement(
            conn, variant_id, "RESERVATION", quantity, f"reserved as {code}", "customer",
            branch_id, reserved_delta=quantity, reservation_id=new_id,
        )

    return get(new_id)


def _set_status(reservation_id, new_status, release_stock=False, consume_stock=False, actor="staff"):
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
        if not row:
            raise ReservationError("reservation not found")

        stock = conn.execute(
            "SELECT * FROM inventory WHERE variant_id = ? AND branch_id = ?",
            (row["variant_id"], row["branch_id"]),
        ).fetchone()

        if release_stock and stock:
            conn.execute(
                "UPDATE inventory SET reserved = MAX(0, reserved - ?) WHERE id = ?",
                (row["quantity"], stock["id"]),
            )
            inventory.record_movement(
                conn, row["variant_id"], "RESERVATION_RELEASE", row["quantity"],
                f"{new_status} {row['code']}", actor, row["branch_id"],
                reserved_delta=-row["quantity"], reservation_id=reservation_id)

        if consume_stock and stock:
            conn.execute(
                """UPDATE inventory
                   SET on_hand = MAX(0, on_hand - ?), reserved = MAX(0, reserved - ?),
                       updated_at = datetime('now')
                   WHERE id = ?""",
                (row["quantity"], row["quantity"], stock["id"]),
            )
            inventory.record_movement(
                conn, row["variant_id"], "PICKUP", row["quantity"],
                f"picked up {row['code']}", actor, row["branch_id"],
                on_hand_delta=-row["quantity"], reserved_delta=-row["quantity"],
                reservation_id=reservation_id)
            _write_sale(conn, row)

        # Accept and ready move no stock, but they belong on the timeline: the
        # history exists to explain how a count reached its current value.
        lifecycle = {"accepted": "RESERVATION_ACCEPTED", "ready_for_pickup": "RESERVATION_READY"}
        if new_status in lifecycle:
            inventory.record_movement(
                conn, row["variant_id"], lifecycle[new_status], row["quantity"],
                f"{row['code']}", actor, row["branch_id"], reservation_id=reservation_id)

        conn.execute(
            "UPDATE reservations SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_status, reservation_id),
        )
    return get(reservation_id)


def _write_sale(conn, reservation):
    """A completed pickup is a sale: order, payment and invoice together.

    Name and price are copied in, so deleting the product later cannot rewrite
    what this customer paid. Payment and invoice are mock records -- no money
    moves anywhere.
    """
    variant = conn.execute(
        """SELECT v.*, p.name AS product_name FROM product_variants v
           JOIN products p ON p.id = v.product_id WHERE v.id = ?""",
        (reservation["variant_id"],),
    ).fetchone()
    total = round(variant["price"] * reservation["quantity"], 2)

    cur = conn.execute(
        """INSERT INTO orders
             (store_id, branch_id, customer_id, variant_id, reservation_id,
              product_name, sku, unit_price, quantity, total, channel)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reservation-pickup')""",
        (config.STORE_ID, reservation["branch_id"], reservation["customer_id"],
         reservation["variant_id"], reservation["id"], variant["product_name"],
         variant["sku"], variant["price"], reservation["quantity"], total),
    )
    order_id = cur.lastrowid
    conn.execute(
        "INSERT INTO payments (store_id, order_id, method, amount, status) VALUES (?, ?, ?, ?, ?)",
        (config.STORE_ID, order_id, "cash", total, "captured"),
    )
    conn.execute(
        "INSERT INTO invoices (store_id, order_id, number, amount) VALUES (?, ?, ?, ?)",
        (config.STORE_ID, order_id, f"INV-{order_id:05d}", total),
    )


def _require(reservation_id, allowed):
    row = db.query_one("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
    if not row:
        raise ReservationError("reservation not found")
    if row["status"] not in allowed:
        raise ReservationError(
            f"cannot do that to a {row['status']} reservation")
    return row


def accept(reservation_id, actor="staff"):
    _require(reservation_id, ("pending",))
    return _set_status(reservation_id, "accepted", actor=actor)


def mark_ready(reservation_id, actor="staff"):
    _require(reservation_id, ("pending", "accepted"))
    return _set_status(reservation_id, "ready_for_pickup", actor=actor)


def reject(reservation_id, actor="staff"):
    _require(reservation_id, ("pending", "accepted", "ready_for_pickup"))
    return _set_status(reservation_id, "rejected", release_stock=True, actor=actor)


def cancel(reservation_id, actor="customer"):
    _require(reservation_id, ("pending", "accepted", "ready_for_pickup"))
    return _set_status(reservation_id, "cancelled", release_stock=True, actor=actor)


def complete(reservation_id, actor="staff"):
    """Hand the goods over: stock leaves the building and a sale is recorded."""
    _require(reservation_id, ("accepted", "ready_for_pickup"))
    return _set_status(reservation_id, "completed", consume_stock=True, actor=actor)


def expire_due():
    """Release holds that ran out of time.

    Called before any read of the queue, so the demo self-heals rather than
    leaking stock into holds nobody is coming to collect.
    """
    due = db.query(
        f"""SELECT id FROM reservations
            WHERE status IN ({','.join('?' * len(OPEN_STATES))})
              AND expires_at IS NOT NULL AND expires_at < datetime('now')""",
        OPEN_STATES,
    )
    for row in due:
        try:
            _set_status(row["id"], "expired", release_stock=True, actor="system")
        except ReservationError:
            pass
    return len(due)
