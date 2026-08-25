"""Store profile and configuration."""
import re
from datetime import datetime

import config
import db
from services import audit, inventory
from services.security import require

# The showcase layouts the client knows how to render. Kept here, not just in
# the client, because the value is validated on the way in -- an unrecognised
# type stored in the database would silently fall back to the general layout
# forever with no way to tell "chose general" apart from "typo'd grocery".
SHOWCASE_TYPES = ("general", "grocery", "mall")

# Fields an owner may change from the settings screen. Identity (id) and
# figures the app itself derives (rating, lat/lng) are deliberately absent --
# this is the store's own description of itself, not its scoreboard.
EDITABLE_FIELDS = (
    "name", "type", "tagline", "phone", "email", "address",
    "opens_at", "closes_at", "accent_color",
)


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


def _valid_time(value):
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except (ValueError, TypeError):
        return False


def update(actor, fields):
    """Edit the store's own profile, including which showcase it runs.

    Owner only (settings.edit): the shop type reshapes what every customer
    sees, so it is not a counter-level decision.
    """
    require(actor, "settings.edit")
    existing = db.query_one("SELECT * FROM stores WHERE id = ?", (config.STORE_ID,))
    if not existing:
        raise ValueError("store not found")

    changes = {}
    for key in EDITABLE_FIELDS:
        if key not in fields:
            continue
        value = fields[key]

        if key == "type":
            value = (value or "general").strip().lower()
            if value not in SHOWCASE_TYPES:
                raise ValueError(f"unknown store type: {value}")
        elif key == "name":
            value = (value or "").strip()
            if not value:
                raise ValueError("shop name is required")
        elif key in ("opens_at", "closes_at"):
            if not _valid_time(value):
                raise ValueError(f"{key} must be in HH:MM form")
        elif key == "accent_color":
            value = (value or "").strip()
            if value and not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError("accent_color must be a hex colour like #3d5afe")
        else:
            value = (value or "").strip()

        changes[key] = value

    if changes:
        db.execute(
            f"UPDATE stores SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
            (*changes.values(), config.STORE_ID),
        )
        audit.record(actor, "settings.edit", "store", config.STORE_ID,
                     {"fields": sorted(changes.keys())})
    return profile()
