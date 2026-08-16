"""Dashboard and analytics aggregates.

Everything here reads from orders and inventory_movements rather than from
running totals, so any figure on the dashboard can be traced back to the events
that produced it.
"""
import config
import db
from services import inventory, reservations


def today():
    sales = db.query_one(
        """SELECT COALESCE(SUM(total), 0) AS revenue, COUNT(*) AS orders
           FROM orders WHERE store_id = ? AND date(created_at) = date('now')""",
        (config.STORE_ID,),
    )
    reservations.expire_due()
    open_reservations = db.query_one(
        """SELECT COUNT(*) AS n FROM reservations
           WHERE store_id = ? AND status IN ('pending','accepted','ready')""",
        (config.STORE_ID,),
    )
    pending = db.query_one(
        "SELECT COUNT(*) AS n FROM reservations WHERE store_id = ? AND status = 'pending'",
        (config.STORE_ID,),
    )
    stock = inventory.summary()
    return {
        "revenue": round(sales["revenue"], 2),
        "orders": sales["orders"],
        "reservations": open_reservations["n"],
        "pending_reservations": pending["n"],
        "low_stock": stock["low_stock"],
        "out_of_stock": stock["out_of_stock"],
        "stale_counts": stock["stale"],
    }


def sales_trend(days=7):
    """One point per day, including days with no sales.

    A gap-free series matters: a chart that silently skips quiet days makes a
    flat week look like a busy one.
    """
    rows = {
        r["day"]: r
        for r in db.query(
            """SELECT date(created_at) AS day, SUM(total) AS revenue, COUNT(*) AS orders
               FROM orders
               WHERE store_id = ? AND created_at >= datetime('now', ?)
               GROUP BY date(created_at)""",
            (config.STORE_ID, f"-{days - 1} days"),
        )
    }
    out = []
    for offset in range(days - 1, -1, -1):
        day = db.query_one("SELECT date('now', ?) AS d", (f"-{offset} days",))["d"]
        row = rows.get(day)
        out.append({
            "day": day,
            "revenue": round(row["revenue"], 2) if row else 0.0,
            "orders": row["orders"] if row else 0,
        })
    return out


def top_products(limit=5):
    return db.query(
        """SELECT product_name, sku, SUM(quantity) AS units, SUM(total) AS revenue
           FROM orders WHERE store_id = ?
           GROUP BY product_name, sku
           ORDER BY revenue DESC LIMIT ?""",
        (config.STORE_ID, limit),
    )


def low_stock(limit=10):
    rows = [r for r in inventory.levels() if r["status"] in ("limited", "out")]
    rows.sort(key=lambda r: (r["available"], r["product_name"]))
    return rows[:limit]


def overview():
    week = sales_trend(7)
    stock = inventory.summary()
    return {
        "today": today(),
        "week_revenue": round(sum(d["revenue"] for d in week), 2),
        "week_orders": sum(d["orders"] for d in week),
        "trend": week,
        "top_products": top_products(),
        "low_stock": low_stock(),
        "inventory": stock,
        "recent_movements": inventory.movements(limit=8),
    }
