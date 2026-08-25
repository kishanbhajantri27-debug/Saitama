"""Fair-use policy for holds.

A hold takes a unit off the shelf for an hour and pays the store nothing, so
the shop needs some protection from one shopper reserving the whole aisle.

The allowance is deliberately shaped around intent rather than volume: it is
spent on *distinct product types* per day, so putting the same item back on
hold after it lapsed costs nothing, while spreading holds across the catalogue
is what runs it down. Quantity is not counted either -- five kilos of one rice
is one shopping decision, not five.

Nothing in here touches stock, and a shopper inside their allowance takes
exactly the same path through reservations.create() as before. This module
only ever answers "is this allowed, and what should we say if not".

Usage is counted from the reservations table rather than from a running total,
so a cancelled hold, a rebuilt database or a hand-edited row can never leave
the counter disagreeing with the history it came from.
"""
from datetime import date, timedelta

import config
import db

# Cancelled and expired holds still count. The cost to the store was already
# paid the moment the stock came off the shelf, and forgiving them would make
# the cap trivially avoidable: hold, cancel, repeat.
#
# Prepaid (buy-now) rows are excluded: the allowance rations holds that cost
# the store real shelf space for free, and a bought item already paid for
# that space, so it is not the thing this policy is protecting against.
COUNTED_SQL = """
FROM reservations r
JOIN product_variants v ON v.id = r.variant_id
WHERE r.customer_id = ? AND date(r.created_at) = ? AND r.prepaid = 0
"""


class HoldLimitReached(Exception):
    """The shopper is out of allowance for today.

    Carries the whole quota with it so the caller can explain the situation
    -- how much was used, whether this is becoming a habit, how to continue --
    without going back to the database for any of it.
    """

    def __init__(self, quota):
        super().__init__(quota["message"])
        self.quota = quota


def _today():
    return db.query_one("SELECT date('now') AS d")["d"]


def types_used(customer_id, day=None):
    """Distinct products this shopper has put on hold today."""
    day = day or _today()
    row = db.query_one(
        f"SELECT COUNT(DISTINCT v.product_id) AS n {COUNTED_SQL}", (customer_id, day))
    return row["n"] if row else 0


def held_product_ids(customer_id, day=None):
    """Which products those were -- so re-holding one can be allowed through."""
    day = day or _today()
    return {
        r["product_id"]
        for r in db.query(f"SELECT DISTINCT v.product_id {COUNTED_SQL}", (customer_id, day))
    }


def extra_allowance(customer_id, day=None):
    """Whatever passes the shopper bought for today, added together."""
    day = day or _today()
    row = db.query_one(
        """SELECT COALESCE(SUM(extra_types), 0) AS n FROM hold_passes
           WHERE customer_id = ? AND day = ?""",
        (customer_id, day),
    )
    return row["n"] if row else 0


def capped_streak(customer_id):
    """Consecutive days, up to and including today, that the shopper filled.

    A live run, not a tally over a window: filling the allowance on Monday and
    Wednesday but not Tuesday is somebody shopping, whereas three days without
    a break is somebody using holds as storage. A single quiet day ends it.

    Measured against the base allowance rather than the extended one. Somebody
    who bought a pass has already settled up for that day, and counting it
    against them as well would be talking out of both sides of our mouth.
    """
    rows = db.query(
        """SELECT date(r.created_at) AS day, COUNT(DISTINCT v.product_id) AS n
           FROM reservations r
           JOIN product_variants v ON v.id = r.variant_id
           WHERE r.customer_id = ? AND r.prepaid = 0
           GROUP BY day
           HAVING n >= ?
           ORDER BY day DESC""",
        (customer_id, config.HOLD_TYPES_PER_DAY),
    )
    full = {date.fromisoformat(r["day"]) for r in rows}
    if not full:
        return []

    # Today may not be full yet, so a run ending yesterday is still live -- it
    # is what lets the warning appear before the third day is spent rather than
    # only after. Anything older than that has already been broken by a gap.
    today = date.fromisoformat(_today())
    cursor = today if today in full else today - timedelta(days=1)
    if cursor not in full:
        return []

    streak = []
    while cursor in full:
        streak.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return list(reversed(streak))


def quota(customer_id):
    """The shopper's standing with the hold allowance, ready to render."""
    day = _today()
    base = config.HOLD_TYPES_PER_DAY
    extra = extra_allowance(customer_id, day)
    limit = base + extra
    used = types_used(customer_id, day)
    remaining = max(0, limit - used)

    streak = capped_streak(customer_id)
    warn = len(streak) >= config.HOLD_REPEAT_STREAK_DAYS

    if remaining:
        message = f"{remaining} of {limit} item types left to hold today."
    else:
        message = (
            f"You have held {used} different items today, which is the daily limit of {limit}."
        )

    return {
        "day": day,
        "limit": limit,
        "base_limit": base,
        "extra_from_passes": extra,
        "used": used,
        "remaining": remaining,
        "hold_minutes": config.RESERVATION_MINUTES,
        "product_ids": sorted(held_product_ids(customer_id, day)),
        "capped_days": streak,
        "streak_days": len(streak),
        "streak_limit": config.HOLD_REPEAT_STREAK_DAYS,
        "charges_warning": warn,
        "charges_message": (
            f"You have used the full hold limit {len(streak)} days in a row. Holding stock "
            f"this often keeps it off the shelf for other shoppers, so the store may start "
            f"applying a charge for it."
        ) if warn else "",
        "message": message,
        "pass_price": config.HOLD_PASS_PRICE,
        "pass_extra_types": config.HOLD_PASS_EXTRA_TYPES,
        "pass_qr_is_demo": config.HOLD_PASS_QR_IS_DEMO,
    }


def product_id_for_variant(variant_id):
    row = db.query_one("SELECT product_id FROM product_variants WHERE id = ?", (variant_id,))
    return row["product_id"] if row else None


def check(customer_id, variant_id):
    """Gate one hold. Returns the quota; raises HoldLimitReached if it is spent.

    An item already held today is always let through, whatever the counter
    says -- it costs no new allowance, and refusing to let someone re-hold the
    rice they held this morning would read as a bug rather than a policy.
    """
    state = quota(customer_id)
    if state["remaining"] > 0:
        return state

    product_id = product_id_for_variant(variant_id)
    if product_id is not None and product_id in set(state["product_ids"]):
        return state

    raise HoldLimitReached(state)


def grant_pass(customer_id, reference="demo"):
    """Record that the shopper bought more allowance for today.

    Deliberately dumb: this app never sees the payment, so there is nothing to
    verify. Wiring a real gateway means calling this from its webhook instead
    of from the button, and passing the real reference through.
    """
    day = _today()
    db.execute(
        """INSERT INTO hold_passes (store_id, customer_id, day, extra_types, reference)
           VALUES (?, ?, ?, ?, ?)""",
        (config.STORE_ID, customer_id, day, config.HOLD_PASS_EXTRA_TYPES, reference or "demo"),
    )
    return quota(customer_id)
