"""Authorization over HTTP.

These are the tests that matter most: they call the endpoints directly, the way
somebody bypassing the UI would, and check the server refuses regardless of
what the interface happens to show.
"""
import pytest

# (method, path, permission-holding roles). Anyone outside the set gets a 403,
# and no token at all gets a 401.
PROTECTED = [
    ("GET", "/api/inventory", {"owner", "manager", "staff"}),
    ("GET", "/api/inventory/summary", {"owner", "manager", "staff"}),
    ("GET", "/api/inventory/movements", {"owner", "manager", "staff"}),
    ("GET", "/api/analytics/today", {"owner", "manager"}),
    ("GET", "/api/analytics/overview", {"owner", "manager"}),
    ("GET", "/api/customers", {"owner", "manager", "staff"}),
    ("GET", "/api/staff", {"owner", "manager"}),
    ("GET", "/api/audit", {"owner", "manager"}),
]


class TestUnauthenticatedAccess:
    @pytest.mark.parametrize("method,path,_roles", PROTECTED)
    def test_no_token_is_rejected(self, client, method, path, _roles):
        assert client.open(path, method=method).status_code == 401

    def test_garbage_token_is_rejected(self, client):
        res = client.get("/api/inventory", headers={"X-Staff-Token": "not-a-real-token"})
        assert res.status_code == 401

    def test_empty_token_is_rejected(self, client):
        assert client.get("/api/inventory", headers={"X-Staff-Token": ""}).status_code == 401

    def test_writes_are_rejected_without_a_token(self, client, a_variant):
        assert client.post(f"/api/inventory/{a_variant['id']}/movement",
                           json={"kind": "add", "quantity": 5}).status_code == 401
        assert client.post("/api/demo/reset").status_code == 401
        assert client.post("/api/staff", json={"username": "x", "password": "y"}).status_code == 401


class TestRoleBoundaries:
    @pytest.mark.parametrize("method,path,allowed", PROTECTED)
    def test_each_role_gets_the_right_answer(self, client, login, method, path, allowed):
        for role, password in [("owner", "owner123"), ("manager", "manager123"),
                               ("staff", "staff123")]:
            headers = login(role, password)
            status = client.open(path, method=method, headers=headers).status_code
            if role in allowed:
                assert status == 200, f"{role} should reach {path}, got {status}"
            else:
                assert status == 403, f"{role} should be refused {path}, got {status}"


class TestInventoryPermissions:
    def test_clerk_may_receive_stock(self, client, staff_headers, a_variant):
        res = client.post(f"/api/inventory/{a_variant['id']}/movement",
                          headers=staff_headers, json={"kind": "add", "quantity": 3})
        assert res.status_code == 200

    def test_clerk_may_not_set_an_absolute_count(self, client, staff_headers, a_variant):
        """A stock-take can hide a discrepancy, so it needs a supervisor."""
        res = client.post(f"/api/inventory/{a_variant['id']}/movement",
                          headers=staff_headers, json={"kind": "adjust", "quantity": 99})
        assert res.status_code == 403
        assert res.get_json()["permission"] == "inventory.stocktake"

    def test_manager_may_set_an_absolute_count(self, client, manager_headers, a_variant):
        res = client.post(f"/api/inventory/{a_variant['id']}/movement",
                          headers=manager_headers, json={"kind": "adjust", "quantity": 9})
        assert res.status_code == 200

    def test_refused_write_changes_nothing(self, client, staff_headers, a_variant):
        before = client.get(f"/api/products/{a_variant['product_id']}").get_json()
        client.post(f"/api/inventory/{a_variant['id']}/movement",
                    headers=staff_headers, json={"kind": "adjust", "quantity": 99})
        after = client.get(f"/api/products/{a_variant['product_id']}").get_json()
        assert before == after


class TestReservationPermissions:
    @pytest.fixture
    def pending_reservation(self, client, a_variant, a_customer):
        res = client.post("/api/reservations", json={
            "variant_id": a_variant["id"], "customer_id": a_customer["id"], "quantity": 1})
        assert res.status_code == 201
        return res.get_json()

    def test_clerk_may_accept(self, client, staff_headers, pending_reservation):
        res = client.post(f"/api/reservations/{pending_reservation['id']}/accept",
                          headers=staff_headers)
        assert res.status_code == 200
        assert res.get_json()["status"] == "accepted"

    def test_clerk_may_not_reject(self, client, staff_headers, pending_reservation):
        """Turning a customer away is a manager's call."""
        res = client.post(f"/api/reservations/{pending_reservation['id']}/reject",
                          headers=staff_headers)
        assert res.status_code == 403

    def test_manager_may_reject(self, client, manager_headers, pending_reservation):
        res = client.post(f"/api/reservations/{pending_reservation['id']}/reject",
                          headers=manager_headers)
        assert res.status_code == 200
        assert res.get_json()["status"] == "rejected"

    def test_refused_reject_leaves_the_hold_in_place(self, client, staff_headers,
                                                     pending_reservation, a_variant):
        before = client.get(f"/api/products/{a_variant['product_id']}").get_json()
        client.post(f"/api/reservations/{pending_reservation['id']}/reject", headers=staff_headers)
        after = client.get(f"/api/products/{a_variant['product_id']}").get_json()
        assert before["available"] == after["available"]

    def test_anonymous_cannot_drive_the_lifecycle(self, client, pending_reservation):
        for action in ("accept", "ready", "reject", "complete"):
            res = client.post(f"/api/reservations/{pending_reservation['id']}/{action}")
            assert res.status_code == 401, f"{action} should need sign-in"


class TestStaffAdminEndpoints:
    def test_manager_may_view_but_not_create(self, client, manager_headers):
        assert client.get("/api/staff", headers=manager_headers).status_code == 200
        res = client.post("/api/staff", headers=manager_headers,
                          json={"name": "X", "username": "x1", "password": "pass1234"})
        assert res.status_code == 403

    def test_owner_may_create(self, client, owner_headers):
        res = client.post("/api/staff", headers=owner_headers,
                          json={"name": "X", "username": "x1", "password": "pass1234",
                                "role": "staff"})
        assert res.status_code == 201
        assert "password_hash" not in res.get_json()

    def test_clerk_cannot_even_list(self, client, staff_headers):
        assert client.get("/api/staff", headers=staff_headers).status_code == 403

    def test_response_never_carries_a_hash(self, client, owner_headers):
        body = client.get("/api/staff", headers=owner_headers).get_data(as_text=True)
        assert "password_hash" not in body
        assert "scrypt$" not in body


class TestSessionInvalidation:
    def test_disabling_kills_an_open_session(self, client, owner_headers, staff_headers, clerk):
        assert client.get("/api/inventory", headers=staff_headers).status_code == 200
        client.put(f"/api/staff/{clerk['id']}/status", headers=owner_headers,
                   json={"status": "disabled"})
        # The token was valid a moment ago; it must stop working at once.
        assert client.get("/api/inventory", headers=staff_headers).status_code == 401

    def test_deleting_kills_an_open_session(self, client, owner_headers, staff_headers, clerk):
        client.delete(f"/api/staff/{clerk['id']}", headers=owner_headers)
        assert client.get("/api/inventory", headers=staff_headers).status_code == 401

    def test_demotion_removes_the_old_powers(self, client, owner_headers, manager_headers,
                                             manager):
        assert client.get("/api/analytics/today", headers=manager_headers).status_code == 200
        client.put(f"/api/staff/{manager['id']}/role", headers=owner_headers,
                   json={"role": "staff"})
        # Session revoked on role change, so this reads as unauthenticated.
        assert client.get("/api/analytics/today", headers=manager_headers).status_code == 401

    def test_promotion_grants_new_powers_on_next_sign_in(self, client, owner_headers, login,
                                                         clerk):
        client.put(f"/api/staff/{clerk['id']}/role", headers=owner_headers,
                   json={"role": "manager"})
        headers = login("staff", "staff123")
        assert client.get("/api/analytics/today", headers=headers).status_code == 200

    def test_logout_invalidates(self, client, staff_headers):
        client.post("/api/session/staff/logout", headers=staff_headers)
        assert client.get("/api/inventory", headers=staff_headers).status_code == 401


class TestLoginEndpoint:
    def test_login_returns_a_token_and_permissions(self, client):
        res = client.post("/api/session/staff",
                          json={"username": "owner", "password": "owner123"})
        body = res.get_json()
        assert res.status_code == 200
        assert body["token"]
        assert body["user"]["role"] == "owner"
        assert "staff.create" in body["permissions"]

    def test_login_response_has_no_secrets(self, client):
        text = client.post("/api/session/staff",
                           json={"username": "owner", "password": "owner123"}
                           ).get_data(as_text=True)
        assert "owner123" not in text
        assert "password_hash" not in text
        assert "scrypt$" not in text

    @pytest.mark.parametrize("payload", [
        {"username": "owner", "password": "wrong"},
        {"username": "ghost", "password": "owner123"},
        {"username": "exstaff", "password": "disabled123"},
        {},
    ])
    def test_failures_are_indistinguishable(self, client, payload):
        """Same status and message, so usernames cannot be enumerated."""
        res = client.post("/api/session/staff", json=payload)
        assert res.status_code == 401
        assert res.get_json()["error"] == "wrong username or password"

    def test_session_me_reports_role_and_permissions(self, client, staff_headers):
        body = client.get("/api/session/me", headers=staff_headers).get_json()
        assert body["user"]["role"] == "staff"
        assert "inventory.adjust" in body["permissions"]
        assert "staff.create" not in body["permissions"]


class TestPublicEndpointsStayPublic:
    """Locking down staff routes must not break the customer app."""

    @pytest.mark.parametrize("path", [
        "/api/config", "/api/store", "/api/products", "/api/categories",
        "/api/me", "/api/permissions",
    ])
    def test_reachable_without_a_token(self, client, path):
        assert client.get(path).status_code == 200

    def test_a_customer_can_still_reserve(self, client, a_variant, a_customer):
        res = client.post("/api/reservations", json={
            "variant_id": a_variant["id"], "customer_id": a_customer["id"], "quantity": 1})
        assert res.status_code == 201

    def test_a_customer_can_read_their_own_reservations(self, client, a_customer):
        assert client.get(f"/api/reservations?customer_id={a_customer['id']}").status_code == 200

    def test_the_full_queue_still_needs_sign_in(self, client):
        assert client.get("/api/reservations").status_code == 401
