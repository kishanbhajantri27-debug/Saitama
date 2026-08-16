"""Session handling and route-level authorization.

Tokens are opaque random strings mapped to a staff id. The mapping lives in
memory, so restarting signs everyone out -- acceptable here, and honest about
not being a durable session store.

The important property: a token records *who*, never *what they may do*. Every
request re-reads the account from the database, so disabling someone or
changing their role takes effect on their next call rather than whenever their
session happens to end.
"""
import secrets
import threading
from functools import wraps

from flask import g, jsonify, request

from services import audit, staff
from services.security import NotAuthenticated, PermissionDenied, require

# token -> employee id. Guarded because Flask serves on several threads.
_SESSIONS = {}
_LOCK = threading.Lock()


def issue_token(employee_id):
    token = secrets.token_urlsafe(32)
    with _LOCK:
        _SESSIONS[token] = employee_id
    return token


def revoke(token):
    with _LOCK:
        _SESSIONS.pop(token, None)


def revoke_all_for(employee_id):
    """Drop every session belonging to one account.

    Called when an account is disabled or deleted so existing tokens stop
    working immediately, rather than lasting until the process restarts.
    """
    with _LOCK:
        for token in [t for t, eid in _SESSIONS.items() if eid == employee_id]:
            _SESSIONS.pop(token, None)


def _token_from_request():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return request.headers.get("X-Staff-Token", "")


def current_actor():
    """The staff row behind this request, or None.

    Re-read every time on purpose. Caching the role on the token would let a
    demoted or disabled person keep their old powers until they signed out.
    """
    if "actor" in g:
        return g.actor

    token = _token_from_request()
    actor = None
    if token:
        with _LOCK:
            employee_id = _SESSIONS.get(token)
        if employee_id:
            row = staff.get(employee_id)
            if not row or row["status"] != "active":
                # Account disabled or deleted since the token was issued.
                revoke(token)
            else:
                actor = row
    g.actor = actor
    return actor


def is_staff():
    return current_actor() is not None


def require_permission(permission, entity_type=""):
    """Gate a route on a permission.

    This is a second line rather than the only one: services enforce the same
    permission themselves, so a caller who reaches a service another way is
    still stopped. Checking here as well means unauthorized requests are
    refused before they touch business logic.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            actor = current_actor()
            try:
                require(actor, permission)
            except NotAuthenticated as err:
                return jsonify(error=str(err)), 401
            except PermissionDenied as err:
                audit.record_denied(
                    actor, permission, entity_type,
                    kwargs.get("employee_id") or kwargs.get("variant_id")
                    or kwargs.get("reservation_id") or "")
                return jsonify(error=str(err), permission=permission), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_staff(view):
    """Signed in as anyone. For endpoints with no finer permission."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_actor():
            return jsonify(error="store mode sign-in required"), 401
        return view(*args, **kwargs)

    return wrapped
