"""Store/tenant configuration.

Every store-scoped row carries a store_id. This child app runs one store, so
the id is fixed here -- but nothing downstream assumes that, which is what lets
the same code become one tenant among many on the parent platform.
"""
import os

STORE_ID = os.environ.get("STORE_ID", "STORE-CMR-001")
BRANCH_ID = os.environ.get("BRANCH_ID", "BRANCH-BLR-01")

# How long a customer's hold survives before the stock is released again.
# The shelf, the buttons and the confirmation all promise an hour; this is the
# number that has to agree with them.
RESERVATION_MINUTES = int(os.environ.get("RESERVATION_MINUTES") or 60)

# ---- Hold fair-use ----
# A hold takes a unit off the shelf for an hour and pays the store nothing, so
# one shopper reserving the whole aisle is a real cost to somebody. The
# allowance is spent on distinct product *types* per day rather than on holds:
# putting the same item back on hold after it lapsed is the same intent and
# should cost nothing, while spreading holds across the catalogue is what runs
# the allowance down.
HOLD_TYPES_PER_DAY = int(os.environ.get("HOLD_TYPES_PER_DAY") or 5)

# Filling the allowance once is a busy shopping day. Filling it three days
# running is a habit the store may want to charge for -- so the shopper is told
# while it is still a warning, rather than being surprised by a bill later.
#
# Counted as a live streak rather than as days-out-of-a-window: a shopper who
# fills it Monday, skips Tuesday and fills it Wednesday is shopping, not
# parking stock, and should not be dunned for it.
HOLD_REPEAT_STREAK_DAYS = int(os.environ.get("HOLD_REPEAT_STREAK_DAYS") or 3)

# What one pass buys: a second allowance for the rest of the same day.
HOLD_PASS_EXTRA_TYPES = int(os.environ.get("HOLD_PASS_EXTRA_TYPES") or 5)
HOLD_PASS_PRICE = os.environ.get("HOLD_PASS_PRICE") or "₹20"

# The QR shown when a shopper wants to keep holding past the allowance.
#
# This is a placeholder and is built to be swapped: put the store's real UPI
# (or any payment) string in HOLD_PASS_QR_PAYLOAD and the same screen becomes a
# live checkout with no code change. Until then the payload says DEMO in the
# note field, and nothing anywhere reads, verifies or settles it -- so no money
# moves in either direction.
HOLD_PASS_QR_PAYLOAD = os.environ.get("HOLD_PASS_QR_PAYLOAD") or (
    "upi://pay?pa=demo@cmrstore&pn=CMR%20Store&am=20.00&cu=INR"
    "&tn=Hold%20pass%20-%20DEMO%20QR%2C%20not%20a%20real%20payee"
)

# True while the placeholder above is still in use. The UI leans on this to
# label the QR as a demo, so replacing the payload also removes the label.
HOLD_PASS_QR_IS_DEMO = not os.environ.get("HOLD_PASS_QR_PAYLOAD")

# Stock freshness thresholds, in minutes. Under FRESH it is trusted, over STALE
# it is shown with a warning, between the two it is simply aged.
FRESH_MINUTES = 30
STALE_MINUTES = 180

# Availability bands used across both modes.
LOW_STOCK_AT = 3

CURRENCY = "₹"

# Store mode now uses per-employee accounts with roles, seeded by seed.py.
# The shared passcode that used to gate it is gone: it could not identify who
# did something, which made an audit trail impossible.

# Demo mode offers one-tap sign-in as each role so the showcase can be handed
# to anyone. It is a deliberate authentication bypass and it is gated here.
#
# Set DEMO_MODE=false for anything real. That closes the bypass endpoint, and
# because the seeded accounts then hold randomly generated passwords that are
# printed once and never stored in plaintext, nobody can sign in until an owner
# password is set explicitly. Locked-out-by-default is the correct posture for
# a system leaving demo.
DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() not in ("false", "0", "no")

# Set only when running behind a proxy you control. Off by default: a client
# can send X-Forwarded-For itself, so trusting it without a proxy in front
# would let anyone fake a new address per request and walk past rate limits.
TRUST_PROXY = os.environ.get("TRUST_PROXY", "false").lower() in ("true", "1", "yes")

# Seeded account passwords. Set these to pin them; leave unset and seed.py
# generates strong random ones instead of shipping known values in the repo.
DEMO_PASSWORDS = {
    "owner": os.environ.get("DEMO_OWNER_PASSWORD"),
    "manager": os.environ.get("DEMO_MANAGER_PASSWORD"),
    "staff": os.environ.get("DEMO_STAFF_PASSWORD"),
    "exstaff": os.environ.get("DEMO_EXSTAFF_PASSWORD"),
}

# The parent platform's credential for this store -- a shared secret, not a
# staff session, because the parent is a machine, not an employee. Unset by
# default: an empty token would otherwise mean "compare against ''", which a
# request sending no token at all would trivially satisfy. Absent means the
# integration is off, not open.
PARENT_TOKEN = os.environ.get("PARENT_TOKEN") or None
