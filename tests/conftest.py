"""Test fixtures.

Every test runs against a fresh throwaway database. STORE_DB_PATH is set
before any project module is imported, because db.py reads it at import time --
getting that order wrong would point the suite at the real demo database.
"""
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix="store-tests-")
os.environ["STORE_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ.setdefault("ADMIN_PASS", "test-only-not-a-real-secret")

import db  # noqa: E402
import seed  # noqa: E402
from services import staff  # noqa: E402
from services.security import SYSTEM  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """A clean, seeded database per test, so order never matters."""
    db.reset()
    seed.run(force=True)
    yield
    db.reset()


@pytest.fixture
def owner():
    return staff.get_by_username("owner")


@pytest.fixture
def manager():
    return staff.get_by_username("manager")


@pytest.fixture
def clerk():
    """Named 'clerk' because 'staff' is already the module."""
    return staff.get_by_username("staff")


@pytest.fixture
def disabled_user():
    return staff.get_by_username("exstaff")


@pytest.fixture
def system():
    return SYSTEM


@pytest.fixture
def app():
    import app as app_module
    app_module.app.config.update(TESTING=True)
    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    """Sign in over HTTP and return a header dict for authenticated calls."""
    def _login(username, password):
        res = client.post("/api/session/staff",
                          json={"username": username, "password": password})
        assert res.status_code == 200, f"login failed for {username}: {res.data}"
        return {"X-Staff-Token": res.get_json()["token"]}
    return _login


@pytest.fixture
def owner_headers(login):
    return login("owner", "owner123")


@pytest.fixture
def manager_headers(login):
    return login("manager", "manager123")


@pytest.fixture
def staff_headers(login):
    return login("staff", "staff123")


@pytest.fixture
def a_variant():
    """A variant with stock, for inventory and reservation tests."""
    from services import catalog
    return catalog.find_by_code("NIK-AM-092")


@pytest.fixture
def a_customer():
    from services import customers
    return customers.demo_customer()
