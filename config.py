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
