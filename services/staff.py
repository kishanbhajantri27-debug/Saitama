"""Staff accounts: creation, authentication, role changes, disabling.

Passwords are stored as salted scrypt digests. The plaintext exists only for
the length of a login call and is never logged, audited or returned.
"""
import hashlib
import os
import secrets

import config
import db
from services import audit
from services.security import (OWNER, PermissionDenied, is_valid_role, require)

# scrypt parameters. n=2**14 keeps a login around a few tens of milliseconds --
# slow enough to make guessing expensive, fast enough not to be noticed.
_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32

# Columns that may leave this module. password_hash is absent on purpose, so a
# caller cannot accidentally serialise it into a response or a log line.
PUBLIC_FIELDS = (
    "id", "store_id", "name", "username", "role", "status",
    "last_login_at", "created_at", "disabled_at",
)


def hash_password(password):
    if not password or len(str(password)) < 4:
        raise ValueError("password must be at least 4 characters")
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        str(password).encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    """Constant-time check of a password against a stored digest."""
    try:
        scheme, n, r, p, salt_hex, digest_hex = str(stored).split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            str(password or "").encode(), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)))
        return secrets.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, AttributeError, TypeError):
        # A malformed or missing hash is a failed login, never an exception
        # that could be timed or used to distinguish accounts.
        return False


def public(row):
    """Strip an employee row down to what is safe to hand out."""
    if not row:
        return None
    return {k: row[k] for k in PUBLIC_FIELDS if k in row}


def get(employee_id):
    return db.query_one("SELECT * FROM employees WHERE id = ?", (employee_id,))


def get_by_username(username):
    return db.query_one(
        "SELECT * FROM employees WHERE lower(username) = lower(?)", ((username or "").strip(),))


def list_all(actor=None, include_disabled=True):
    if actor is not None:
        require(actor, "staff.view")
    sql = "SELECT * FROM employees WHERE store_id = ?"
    params = [config.STORE_ID]
    if not include_disabled:
        sql += " AND status = 'active'"
    sql += " ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, name"
    return [public(r) for r in db.query(sql, tuple(params))]


def authenticate(username, password):
    """Return the staff row on success, or None.

    Failure is deliberately indistinguishable between "no such user", "wrong
    password" and "account disabled": a login screen that tells an attacker
    which usernames exist has done half their work.
    """
    row = get_by_username(username)
    if not row:
        # Hash anyway so a missing username does not return measurably faster
        # than a wrong password.
        verify_password(password, f"scrypt${_N}${_R}${_P}{'$' + '00' * 16}${'00' * 32}")
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    if row["status"] != "active":
        return None
    db.execute(
        "UPDATE employees SET last_login_at = datetime('now') WHERE id = ?", (row["id"],))
    return row


def create(actor, name, username, password, role="staff"):
    require(actor, "staff.create")
    username = (username or "").strip()
    if not username:
        raise ValueError("username is required")
    if not is_valid_role(role):
        raise ValueError(f"unknown role: {role}")
    if get_by_username(username):
        raise ValueError("that username is already taken")

    _, new_id = db.execute(
        """INSERT INTO employees (store_id, name, username, password_hash, role)
           VALUES (?, ?, ?, ?, ?)""",
        (config.STORE_ID, (name or username).strip(), username, hash_password(password), role),
    )
    # Note the absence of the password in the detail: only the role matters
    # for the trail.
    audit.record(actor, "staff.create", "employee", new_id,
                 {"username": username, "role": role})
    return public(get(new_id))


def set_role(actor, employee_id, role):
    require(actor, "staff.edit")
    if not is_valid_role(role):
        raise ValueError(f"unknown role: {role}")
    target = get(employee_id)
    if not target:
        raise ValueError("staff member not found")

    # The last active owner cannot be demoted: a store with no owner has no way
    # to grant anyone the permissions needed to fix it.
    if target["role"] == OWNER and role != OWNER and _active_owner_count() <= 1:
        raise ValueError("cannot change the role of the only active owner")

    db.execute("UPDATE employees SET role = ? WHERE id = ?", (role, employee_id))
    audit.record(actor, "staff.set_role", "employee", employee_id,
                 {"from": target["role"], "to": role, "username": target["username"]})
    return public(get(employee_id))


def set_status(actor, employee_id, status):
    require(actor, "staff.disable")
    if status not in ("active", "disabled"):
        raise ValueError("status must be active or disabled")
    target = get(employee_id)
    if not target:
        raise ValueError("staff member not found")
    if status == "disabled":
        if target["role"] == OWNER and _active_owner_count() <= 1:
            raise ValueError("cannot disable the only active owner")
        if actor and actor.get("id") == employee_id:
            raise ValueError("you cannot disable your own account")

    db.execute(
        """UPDATE employees
           SET status = ?, disabled_at = CASE WHEN ? = 'disabled' THEN datetime('now') ELSE NULL END
           WHERE id = ?""",
        (status, status, employee_id),
    )
    audit.record(actor, f"staff.{status}", "employee", employee_id,
                 {"username": target["username"]})
    return public(get(employee_id))


def set_password(actor, employee_id, password):
    """Change a password. Owners may reset anyone's; anyone may change theirs."""
    own = bool(actor) and actor.get("id") == employee_id
    if not own:
        require(actor, "staff.edit")
    target = get(employee_id)
    if not target:
        raise ValueError("staff member not found")

    db.execute("UPDATE employees SET password_hash = ? WHERE id = ?",
               (hash_password(password), employee_id))
    # The trail records that a password changed, never what it changed to.
    audit.record(actor, "staff.password_change", "employee", employee_id,
                 {"username": target["username"], "self_service": own})
    return public(get(employee_id))


def delete(actor, employee_id):
    require(actor, "staff.edit")
    target = get(employee_id)
    if not target:
        raise ValueError("staff member not found")
    if target["role"] == OWNER and _active_owner_count() <= 1:
        raise ValueError("cannot delete the only active owner")
    if actor and actor.get("id") == employee_id:
        raise ValueError("you cannot delete your own account")

    db.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    # The audit rows this person generated survive: actor_id has no foreign key
    # precisely so history is not erased along with the account.
    audit.record(actor, "staff.delete", "employee", employee_id,
                 {"username": target["username"], "role": target["role"]})
    return True


def _active_owner_count():
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM employees WHERE role = ? AND status = 'active'", (OWNER,))
    return row["n"] if row else 0
