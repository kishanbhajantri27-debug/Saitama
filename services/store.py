"""Store profile and configuration."""
from datetime import datetime

import config
import db
from services import inventory


def profile():
    row = db.query_one("SELECT * FROM stores WHERE id = ?", (config.STORE_ID,))
    if not row:
        return None
    stock = inventory.summary()
    row["products_available"] = stock["available"]
    row["total_products"] = stock["total_products"]
    row["is_open"] = _is_open(row["opens_at"], row["closes_at"])
    row["hours_label"] = f"{_pretty(row['opens_at'])} - {_pretty(row['closes_at'])}"
    row["branches"] = db.query(
        "SELECT * FROM branches WHERE store_id = ?", (config.STORE_ID,))
    return row


def _pretty(hhmm):
    try:
        return datetime.strptime(hhmm, "%H:%M").strftime("%-I:%M %p")
    except (ValueError, TypeError):
        try:  # Windows strftime has no %-I
            return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")
        except (ValueError, TypeError):
            return hhmm or ""


def _is_open(opens_at, closes_at):
    try:
        now = datetime.now().time()
        return (datetime.strptime(opens_at, "%H:%M").time()
                <= now
                <= datetime.strptime(closes_at, "%H:%M").time())
    except (ValueError, TypeError):
        return True
