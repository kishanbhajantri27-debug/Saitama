"""Stock levels, movements and freshness."""
from datetime import datetime, timezone

import config
import db

MOVEMENT_KINDS = ("add", "remove", "adjust", "reserve", "release", "pickup")


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    """SQLite datetime('now') gives naive UTC; make it comparable."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def minutes_since(ts):
    parsed = _parse(ts)
    if parsed is None:
        return None
    return max(0, (_now() - parsed).total_seconds() / 60)


def freshness(updated_at):
    """How much the displayed count can be trusted.

    The point of the spec's status block is that a number is only as good as
    the moment it was taken, so the age travels with it everywhere.
    """
    age = minutes_since(updated_at)
    if age is None:
        return {"level": "unknown", "label": "Never updated", "minutes": None, "stale": True}
    if age < config.FRESH_MINUTES:
        level, stale = "fresh", False
    elif age < config.STALE_MINUTES:
        level, stale = "aging", False
    else:
        level, stale = "stale", True
    return {"level": level, "label": humanise(age), "minutes": round(age), "stale": stale}


def humanise(minutes):
    minutes = int(minutes)
    if minutes < 1:
        return "Updated just now"
    if minutes == 1:
        return "Updated 1 minute ago"
    if minutes < 60:
        return f"Updated {minutes} minutes ago"
    hours = minutes // 60
    if hours == 1:
        return "Updated 1 hour ago"
    if hours < 24:
        return f"Updated {hours} hours ago"
    days = hours // 24
    return "Updated 1 day ago" if days == 1 else f"Updated {days} days ago"


def stock_status(available):
    if available <= 0:
        return "out"
    if available <= config.LOW_STOCK_AT:
        return "limited"
    return "available"


def describe(row):
    """Turn an inventory row into what both modes need to render."""
    on_hand = row.get("on_hand", 0) or 0
    reserved = row.get("reserved", 0) or 0
    available = max(0, on_hand - reserved)
    return {
        "on_hand": on_hand,
        "reserved": reserved,
        "available": available,
        "status": stock_status(available),
        "freshness": freshness(row.get("updated_at")),
        "updated_at": row.get("updated_at"),
    }


def get(variant_id, branch_id=None):
    branch_id = branch_id or config.BRANCH_ID
    return db.query_one(
        "SELECT * FROM inventory WHERE variant_id = ? AND branch_id = ?",
        (variant_id, branch_id),
    )


def ensure_row(conn, variant_id, branch_id=None):
    branch_id = branch_id or config.BRANCH_ID
    conn.execute(
        """INSERT OR IGNORE INTO inventory (store_id, branch_id, variant_id, on_hand, reserved)
           VALUES (?, ?, ?, 0, 0)""",
        (config.STORE_ID, branch_id, variant_id),
    )


def record_movement(conn, variant_id, kind, quantity, note="", actor="system", branch_id=None):
    if kind not in MOVEMENT_KINDS:
        raise ValueError(f"unknown movement kind: {kind}")
    conn.execute(
        """INSERT INTO inventory_movements
             (store_id, branch_id, variant_id, kind, quantity, note, actor)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (config.STORE_ID, branch_id or config.BRANCH_ID, variant_id, kind, quantity, note, actor),
    )


def change_stock(variant_id, kind, quantity, note="", actor="staff", branch_id=None):
    """Add, remove or adjust on-hand stock.

    add/remove move by a delta; adjust sets an absolute count, which is what a
    stock-take produces. Every path writes a movement row.
    """
    branch_id = branch_id or config.BRANCH_ID
    if kind not in ("add", "remove", "adjust"):
        raise ValueError("kind must be add, remove or adjust")
    quantity = int(quantity)
    if kind in ("add", "remove") and quantity < 1:
        raise ValueError("quantity must be at least 1")
    if kind == "adjust" and quantity < 0:
        raise ValueError("count cannot be negative")

    with db.transaction() as conn:
        ensure_row(conn, variant_id, branch_id)
        row = conn.execute(
            "SELECT * FROM inventory WHERE variant_id = ? AND branch_id = ?",
            (variant_id, branch_id),
        ).fetchone()

        if kind == "add":
            new_on_hand = row["on_hand"] + quantity
        elif kind == "remove":
            new_on_hand = row["on_hand"] - quantity
            if new_on_hand < 0:
                raise ValueError(f"cannot remove {quantity}; only {row['on_hand']} on hand")
        else:
            new_on_hand = quantity

        # Stock already promised to a customer cannot be counted away.
        if new_on_hand < row["reserved"]:
            raise ValueError(
                f"{row['reserved']} unit(s) are reserved; on-hand cannot go below that")

        conn.execute(
            "UPDATE inventory SET on_hand = ?, updated_at = datetime('now') WHERE id = ?",
            (new_on_hand, row["id"]),
        )
        record_movement(conn, variant_id, kind, quantity, note, actor, branch_id)

    return get(variant_id, branch_id)


def touch(variant_id, branch_id=None):
    """Mark a count as re-verified without changing it."""
    branch_id = branch_id or config.BRANCH_ID
    db.execute(
        "UPDATE inventory SET updated_at = datetime('now') WHERE variant_id = ? AND branch_id = ?",
        (variant_id, branch_id),
    )
    return get(variant_id, branch_id)


def levels(branch_id=None):
    """Every variant with its stock, for the inventory screen."""
    branch_id = branch_id or config.BRANCH_ID
    rows = db.query(
        """SELECT v.id AS variant_id, v.sku, v.barcode, v.label, v.price,
                  p.id AS product_id, p.name AS product_name, p.brand, p.category, p.image_url,
                  i.on_hand, i.reserved, i.updated_at
           FROM product_variants v
           JOIN products p ON p.id = v.product_id
           LEFT JOIN inventory i ON i.variant_id = v.id AND i.branch_id = ?
           WHERE v.store_id = ?
           ORDER BY p.name, v.label""",
        (branch_id, config.STORE_ID),
    )
    for row in rows:
        row.update(describe(row))
    return rows


def summary(branch_id=None):
    rows = levels(branch_id)
    return {
        "total_products": len({r["product_id"] for r in rows}),
        "total_variants": len(rows),
        "available": sum(1 for r in rows if r["status"] == "available"),
        "low_stock": sum(1 for r in rows if r["status"] == "limited"),
        "out_of_stock": sum(1 for r in rows if r["status"] == "out"),
        "stale": sum(1 for r in rows if r["freshness"]["stale"]),
        "inventory_value": round(sum(r["on_hand"] * r["price"] for r in rows), 2),
    }


def movements(limit=50, variant_id=None):
    if variant_id:
        return db.query(
            """SELECT m.*, v.sku, p.name AS product_name
               FROM inventory_movements m
               JOIN product_variants v ON v.id = m.variant_id
               JOIN products p ON p.id = v.product_id
               WHERE m.variant_id = ? ORDER BY m.created_at DESC, m.id DESC LIMIT ?""",
            (variant_id, limit),
        )
    return db.query(
        """SELECT m.*, v.sku, p.name AS product_name
           FROM inventory_movements m
           JOIN product_variants v ON v.id = m.variant_id
           JOIN products p ON p.id = v.product_id
           ORDER BY m.created_at DESC, m.id DESC LIMIT ?""",
        (limit,),
    )
