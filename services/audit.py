"""Append-only record of who did what.

Two rules hold everywhere in this module:

1. Nothing sensitive is written. Passwords, hashes and tokens never reach an
   audit row -- a log that leaks credentials is worse than no log, because it
   concentrates them somewhere people are less careful about.
2. Writing the record must never break the operation it describes. A failed
   audit write is reported to stderr and swallowed.
"""
import json

import config
import db

# Field names that must never be written to an audit detail, whatever the
# caller passes. Matched loosely so 'new_password' and 'api_token' are caught
# alongside the exact names.
SENSITIVE_HINTS = (
    "password", "passwd", "pass_hash", "password_hash", "hash",
    "token", "secret", "authorization", "auth", "passcode", "salt",
    "api_key", "apikey", "credential", "cookie", "session",
)


def _is_sensitive(key):
    lowered = str(key).lower()
    return any(hint in lowered for hint in SENSITIVE_HINTS)


def scrub(detail):
    """Strip anything that looks like a credential out of a detail payload."""
    if detail is None:
        return ""
    if isinstance(detail, dict):
        cleaned = {
            k: ("[redacted]" if _is_sensitive(k) else v)
            for k, v in detail.items()
        }
        return json.dumps(cleaned, default=str, sort_keys=True)
    return str(detail)


def record(actor, action, entity_type="", entity_id="", detail=None, outcome="ok"):
    """Write one audit row.

    actor may be None for system-initiated work such as reservation expiry;
    the trail says 'system' rather than pretending a person did it.
    """
    actor = actor or {}
    try:
        db.execute(
            """INSERT INTO audit_log
                 (store_id, actor_id, actor_name, actor_role, action,
                  entity_type, entity_id, detail, outcome)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                config.STORE_ID,
                actor.get("id"),
                actor.get("name") or "system",
                actor.get("role") or "system",
                action,
                entity_type,
                str(entity_id or ""),
                scrub(detail),
                outcome,
            ),
        )
    except Exception as err:  # pragma: no cover - defensive
        # Deliberately swallowed: an approval must not fail because its audit
        # row could not be written.
        print(f"[audit] could not record {action}: {err}", flush=True)


def record_denied(actor, permission, entity_type="", entity_id=""):
    """Log a refused attempt.

    Denials are the entries worth having. A run of them against one account is
    the signal that somebody is trying doors, and it is invisible if only
    successes are recorded.
    """
    record(
        actor,
        action=f"denied:{permission}",
        entity_type=entity_type,
        entity_id=entity_id,
        detail={"permission": permission},
        outcome="denied",
    )


def recent(limit=100, actor_id=None, action=None, outcome=None):
    sql = "SELECT * FROM audit_log WHERE store_id = ?"
    params = [config.STORE_ID]
    if actor_id:
        sql += " AND actor_id = ?"
        params.append(actor_id)
    if action:
        sql += " AND action LIKE ?"
        params.append(f"%{action}%")
    if outcome:
        sql += " AND outcome = ?"
        params.append(outcome)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def for_entity(entity_type, entity_id, limit=50):
    return db.query(
        """SELECT * FROM audit_log
           WHERE store_id = ? AND entity_type = ? AND entity_id = ?
           ORDER BY created_at DESC, id DESC LIMIT ?""",
        (config.STORE_ID, entity_type, str(entity_id), limit),
    )
