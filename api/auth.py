"""Authentication for store mode.

Demo-grade on purpose. Customer mode needs no identity at all; store mode is
behind a shared staff passcode. Real per-employee accounts belong to the parent
platform, so this is a seam, not a security model -- which is why the demo
passcode is shown on the sign-in screen.
"""
import os
import secrets
from functools import wraps

from flask import jsonify, request

STAFF_PASSCODE = os.environ.get("STAFF_PASSCODE", "2468")
# Sessions live in memory: restarting the server signs staff out, which is fine
# for a showcase and avoids pretending this is a real auth store.
_SESSIONS = set()


def issue_token():
    token = secrets.token_urlsafe(24)
    _SESSIONS.add(token)
    return token


def revoke(token):
    _SESSIONS.discard(token)


def check_passcode(passcode):
    return secrets.compare_digest(str(passcode or ""), STAFF_PASSCODE)


def _token_from_request():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return request.headers.get("X-Staff-Token", "")


def is_staff():
    return _token_from_request() in _SESSIONS


def require_staff(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_staff():
            return jsonify(error="store mode sign-in required"), 401
        return view(*args, **kwargs)

    return wrapped
