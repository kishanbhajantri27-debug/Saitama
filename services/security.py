"""Roles, permissions and their enforcement.

The matrix below is the single source of truth. Routes, services and the UI all
read from it, so there is exactly one place where "can a manager delete a
product" is answered -- and one place to change it.

Enforcement happens in the service layer, not the route layer. Hiding a button
is a courtesy to the user; refusing the operation is the actual control, and it
has to hold whoever calls it and however they reached it.
"""

OWNER = "owner"
MANAGER = "manager"
STAFF = "staff"
ROLES = (OWNER, MANAGER, STAFF)


class PermissionDenied(Exception):
    """Raised when an actor lacks a permission. Surfaces as HTTP 403."""

    def __init__(self, permission, actor=None):
        self.permission = permission
        self.actor = actor
        who = (actor or {}).get("role", "anonymous")
        super().__init__(f"{who} is not allowed to {permission.replace('_', ' ')}")


class NotAuthenticated(Exception):
    """Raised when there is no signed-in actor at all. Surfaces as HTTP 401."""


# Every permission in the system, mapped to the roles that hold it.
#
# Read as: the named roles may do this, and nobody else. Anything absent from a
# role's set is denied -- there is no implicit inheritance, because a hierarchy
# that grants by seniority makes it too easy to hand out something by accident.
PERMISSIONS = {
    # --- products ---
    "product.view":            {OWNER, MANAGER, STAFF},
    "product.create":          {OWNER, MANAGER},
    "product.edit":            {OWNER, MANAGER},
    "product.delete":          {OWNER},

    # --- inventory ---
    "inventory.view":          {OWNER, MANAGER, STAFF},
    # Receiving and shrinkage are everyday counter work.
    "inventory.adjust":        {OWNER, MANAGER, STAFF},
    # Overwriting a count with an absolute number can paper over a discrepancy,
    # so a stock-take is a supervisor's action rather than a clerk's.
    "inventory.stocktake":     {OWNER, MANAGER},
    "inventory.history.view":  {OWNER, MANAGER, STAFF},

    # --- reservations / holds ---
    "reservation.view":        {OWNER, MANAGER, STAFF},
    "reservation.accept":      {OWNER, MANAGER, STAFF},
    "reservation.ready":       {OWNER, MANAGER, STAFF},
    "reservation.complete":    {OWNER, MANAGER, STAFF},
    # Turning a customer away is a judgement call, not a routine one.
    "reservation.reject":      {OWNER, MANAGER},

    # --- orders / sales ---
    "order.view":              {OWNER, MANAGER, STAFF},
    "order.create":            {OWNER, MANAGER, STAFF},
    # Voiding a sale rewrites takings, so it stops at the owner.
    "order.void":              {OWNER},

    # --- refunds ---
    "refund.create":           {OWNER, MANAGER},
    "refund.approve":          {OWNER},

    # --- customers ---
    "customer.view":           {OWNER, MANAGER, STAFF},
    "customer.edit":           {OWNER, MANAGER},
    "customer.delete":         {OWNER},

    # --- analytics ---
    "analytics.view":          {OWNER, MANAGER},

    # --- settings ---
    "settings.view":           {OWNER, MANAGER},
    "settings.edit":           {OWNER},

    # --- staff administration ---
    "staff.view":              {OWNER, MANAGER},
    "staff.create":            {OWNER},
    "staff.edit":              {OWNER},
    "staff.disable":           {OWNER},

    # --- audit ---
    "audit.view":              {OWNER, MANAGER},

    # --- demo controls ---
    # Wiping the dataset is destructive, so it is owner-only even though the
    # data is only ever demo data.
    "demo.reset":              {OWNER},
}


# Unattended work -- reservation expiry, seeding -- runs as this rather than
# as a person. It is a named constant so every bypass is greppable: if this
# appears anywhere a real user's action is being performed, that is a bug.
SYSTEM = {
    "id": None, "name": "system", "role": "system",
    "status": "active", "is_system": True,
}


def is_system(actor):
    return bool(actor) and actor.get("is_system") is True


def is_valid_role(role):
    return role in ROLES


def can(actor, permission):
    """True if this actor holds the permission.

    An actor is a staff row. Anything falsy, disabled, or carrying an unknown
    role is denied -- the default answer is always no.
    """
    if permission not in PERMISSIONS:
        raise KeyError(f"unknown permission: {permission}")
    if not actor:
        return False
    if actor.get("status") != "active":
        return False
    if is_system(actor):
        return True
    return actor.get("role") in PERMISSIONS[permission]


def require(actor, permission):
    """Enforce a permission or raise.

    Distinguishes "nobody is signed in" from "you are signed in but may not do
    this", because those are different problems for the caller: one is fixed by
    signing in, the other never is.
    """
    if not actor:
        raise NotAuthenticated("sign-in required")
    if actor.get("status") != "active":
        # A disabled account is treated as no account rather than as a
        # permission problem -- it should not hint at what it used to be able
        # to do.
        raise NotAuthenticated("this account is no longer active")
    if not can(actor, permission):
        raise PermissionDenied(permission, actor)
    return True


def permissions_for(role):
    """Everything a role may do. Used by the client to lay out its UI."""
    return sorted(p for p, roles in PERMISSIONS.items() if role in roles)


def matrix():
    """The whole table, for documentation and tests."""
    return {p: sorted(roles) for p, roles in sorted(PERMISSIONS.items())}
