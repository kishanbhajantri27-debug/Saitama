"""Store/tenant configuration.

Every store-scoped row carries a store_id. This child app runs one store, so
the id is fixed here -- but nothing downstream assumes that, which is what lets
the same code become one tenant among many on the parent platform.
"""
import os

STORE_ID = os.environ.get("STORE_ID", "STORE-CMR-001")
BRANCH_ID = os.environ.get("BRANCH_ID", "BRANCH-BLR-01")

# How long a customer's hold survives before the stock is released again.
RESERVATION_MINUTES = int(os.environ.get("RESERVATION_MINUTES") or 30)

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

# Seeded account passwords. Set these to pin them; leave unset and seed.py
# generates strong random ones instead of shipping known values in the repo.
DEMO_PASSWORDS = {
    "owner": os.environ.get("DEMO_OWNER_PASSWORD"),
    "manager": os.environ.get("DEMO_MANAGER_PASSWORD"),
    "staff": os.environ.get("DEMO_STAFF_PASSWORD"),
    "exstaff": os.environ.get("DEMO_EXSTAFF_PASSWORD"),
}
