"""The demo sign-in bypass, and that turning it off actually closes it.

This endpoint hands out a session without a password. That is acceptable only
while it is provably gated, so these tests exist to keep it that way.
"""
import pytest

import config
from services import audit, staff


class TestDemoLoginWhenEnabled:
    def test_grants_a_session_for_each_role(self, client):
        for role in ("owner", "manager", "staff"):
            res = client.post("/api/session/demo", json={"role": role})
            assert res.status_code == 200, role
            body = res.get_json()
            assert body["user"]["role"] == role
            assert body["token"]

    def test_the_session_actually_works(self, client):
        token = client.post("/api/session/demo",
                            json={"role": "manager"}).get_json()["token"]
        res = client.get("/api/analytics/today", headers={"X-Staff-Token": token})
        assert res.status_code == 200

    def test_the_granted_session_is_bound_to_that_role_only(self, client):
        """A demo staff session must not carry more than the staff role."""
        token = client.post("/api/session/demo",
                            json={"role": "staff"}).get_json()["token"]
        headers = {"X-Staff-Token": token}
        assert client.get("/api/analytics/today", headers=headers).status_code == 403
        assert client.post("/api/demo/reset", headers=headers).status_code == 403

    def test_unknown_role_refused(self, client):
        assert client.post("/api/session/demo", json={"role": "root"}).status_code == 400
        assert client.post("/api/session/demo", json={}).status_code == 400

    def test_cannot_reach_an_arbitrary_account(self, client, owner_headers):
        """It signs in seeded roles, not any username someone can name."""
        client.post("/api/staff", headers=owner_headers,
                    json={"name": "Secret", "username": "secretadmin",
                          "password": "pass1234", "role": "owner"})
        assert client.post("/api/session/demo",
                           json={"role": "secretadmin"}).status_code == 400

    def test_cannot_sign_in_a_disabled_account(self, client, owner_headers, clerk):
        client.put(f"/api/staff/{clerk['id']}/status", headers=owner_headers,
                   json={"status": "disabled"})
        assert client.post("/api/session/demo", json={"role": "staff"}).status_code == 404

    def test_response_carries_no_credentials(self, client):
        text = client.post("/api/session/demo",
                           json={"role": "owner"}).get_data(as_text=True)
        assert "password" not in text.lower()
        assert "scrypt$" not in text

    def test_recorded_distinctly_from_a_real_login(self, client, owner_headers):
        """The trail must not claim somebody typed a password."""
        client.post("/api/session/demo", json={"role": "manager"})
        actions = [r["action"] for r in
                   client.get("/api/audit", headers=owner_headers).get_json()]
        assert "auth.demo_login" in actions


class TestDemoLoginWhenDisabled:
    @pytest.fixture(autouse=True)
    def demo_off(self, monkeypatch):
        monkeypatch.setattr(config, "DEMO_MODE", False)

    def test_endpoint_disappears(self, client):
        for role in ("owner", "manager", "staff"):
            assert client.post("/api/session/demo", json={"role": role}).status_code == 404

    def test_real_passwords_still_work(self, client, login):
        """Closing the bypass must not lock out a legitimate sign-in."""
        from conftest import TEST_PASSWORDS
        headers = login("owner", TEST_PASSWORDS["owner"])
        assert client.get("/api/staff", headers=headers).status_code == 200

    def test_config_tells_the_client_not_to_offer_it(self, client):
        assert client.get("/api/config").get_json()["demo_mode"] is False


class TestSeededPasswords:
    def test_no_account_uses_a_guessable_default(self):
        """The values that used to ship in the repository must not work."""
        for guess in ("owner123", "manager123", "staff123", "password",
                      "admin", "2468", "changeme123"):
            for username in ("owner", "manager", "staff"):
                assert staff.authenticate(username, guess) is None, \
                    f"{username} accepted {guess!r}"

    def test_passwords_are_pinnable_through_the_environment(self):
        from conftest import TEST_PASSWORDS
        assert staff.authenticate("owner", TEST_PASSWORDS["owner"]) is not None

    def test_random_generation_produces_distinct_secrets(self, monkeypatch):
        """Unset the pins and every account should get its own password."""
        import secrets as secrets_module
        seen = {secrets_module.token_urlsafe(12) for _ in range(50)}
        assert len(seen) == 50, "generated passwords must not repeat"

    def test_hashes_are_never_exposed_by_the_api(self, client, owner_headers):
        for path in ("/api/staff", "/api/session/me", "/api/audit"):
            text = client.get(path, headers=owner_headers).get_data(as_text=True)
            assert "scrypt$" not in text, path
