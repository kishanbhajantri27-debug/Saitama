"""The audit trail: completeness, and that it holds nothing it shouldn't."""
import json

import pytest

from conftest import TEST_PASSWORDS

from services import audit, inventory, reservations, staff


def actions(rows):
    return [r["action"] for r in rows]


class TestScrubbing:
    """Nothing credential-shaped is ever written, whatever the caller passes."""

    @pytest.mark.parametrize("key", [
        "password", "new_password", "password_hash", "token", "api_token",
        "secret", "client_secret", "authorization", "passcode", "salt",
        "api_key", "credential", "session_cookie",
    ])
    def test_sensitive_keys_are_redacted(self, key):
        out = audit.scrub({key: "super-secret-value", "safe": "kept"})
        assert "super-secret-value" not in out
        assert "[redacted]" in out
        assert "kept" in out

    def test_ordinary_fields_survive(self):
        out = json.loads(audit.scrub({"from": 5, "to": 3, "note": "delivery"}))
        assert out == {"from": 5, "to": 3, "note": "delivery"}

    def test_handles_non_dict_details(self):
        assert audit.scrub("plain text") == "plain text"
        assert audit.scrub(None) == ""

    def test_matching_is_case_insensitive(self):
        assert "shh" not in audit.scrub({"PASSWORD": "shh"})
        assert "shh" not in audit.scrub({"Api_Key": "shh"})


class TestRecording:
    def test_records_who_what_when_and_which_record(self, owner):
        audit.record(owner, "test.action", "widget", 42, {"note": "hello"})
        row = audit.recent(limit=1)[0]
        assert row["actor_id"] == owner["id"]
        assert row["actor_name"] == owner["name"]
        assert row["actor_role"] == "owner"
        assert row["action"] == "test.action"
        assert row["entity_type"] == "widget"
        assert row["entity_id"] == "42"
        assert row["created_at"]

    def test_system_actions_are_attributed_to_system(self):
        audit.record(None, "system.thing")
        assert audit.recent(limit=1)[0]["actor_name"] == "system"

    def test_denials_are_recorded_as_denied(self, clerk):
        audit.record_denied(clerk, "staff.create")
        row = audit.recent(limit=1)[0]
        assert row["outcome"] == "denied"
        assert "staff.create" in row["action"]

    def test_a_broken_write_does_not_raise(self, owner, monkeypatch):
        """An audit failure must never take down the operation it describes."""
        import db
        monkeypatch.setattr(db, "execute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
        audit.record(owner, "should.not.raise")  # must not raise


class TestBusinessActionsAreAudited:
    def test_stock_change_is_recorded(self, owner, a_variant):
        inventory.change_stock(a_variant["id"], "add", 5, note="delivery", actor=owner)
        row = audit.recent(limit=1)[0]
        assert row["action"] == "inventory.add"
        assert row["entity_id"] == str(a_variant["id"])
        assert row["actor_id"] == owner["id"]

    def test_stock_change_records_before_and_after(self, owner, a_variant):
        before = inventory.get(a_variant["id"])["on_hand"]
        inventory.change_stock(a_variant["id"], "add", 4, actor=owner)
        detail = json.loads(audit.recent(limit=1)[0]["detail"])
        assert detail["from"] == before
        assert detail["to"] == before + 4

    def test_reservation_lifecycle_is_recorded(self, owner, a_variant, a_customer):
        r = reservations.create(a_variant["id"], a_customer["id"], 1)
        reservations.accept(r["id"], actor=owner)
        reservations.mark_ready(r["id"], actor=owner)
        reservations.complete(r["id"], actor=owner)
        recorded = actions(audit.recent(limit=10))
        for expected in ("reservation.accept", "reservation.ready", "reservation.complete"):
            assert expected in recorded

    def test_staff_changes_are_recorded(self, owner):
        created = staff.create(owner, "Temp", "temp1", "pass1234", "staff")
        staff.set_role(owner, created["id"], "manager")
        staff.set_status(owner, created["id"], "disabled")
        recorded = actions(audit.recent(limit=10))
        assert "staff.create" in recorded
        assert "staff.set_role" in recorded
        assert "staff.disabled" in recorded

    def test_role_change_records_both_ends(self, owner, clerk):
        staff.set_role(owner, clerk["id"], "manager")
        detail = json.loads(
            [r for r in audit.recent(limit=5) if r["action"] == "staff.set_role"][0]["detail"])
        assert detail["from"] == "staff"
        assert detail["to"] == "manager"


class TestNoSecretsInTheTrail:
    def test_account_creation_does_not_store_the_password(self, owner):
        staff.create(owner, "Secret Person", "secretive", "hunter2-very-secret", "staff")
        for row in audit.recent(limit=10):
            assert "hunter2-very-secret" not in json.dumps(dict(row))

    def test_password_change_records_the_event_not_the_value(self, owner, clerk):
        staff.set_password(owner, clerk["id"], "brand-new-secret-value")
        row = [r for r in audit.recent(limit=5) if r["action"] == "staff.password_change"][0]
        assert "brand-new-secret-value" not in json.dumps(dict(row))
        assert row["entity_id"] == str(clerk["id"])

    def test_no_hash_ever_appears(self, owner):
        staff.create(owner, "Hashy", "hashy", "pass1234", "staff")
        blob = json.dumps([dict(r) for r in audit.recent(limit=20)])
        assert "scrypt$" not in blob

    def test_failed_login_does_not_record_the_attempted_password(self, client):
        client.post("/api/session/staff",
                    json={"username": "owner", "password": "guessed-wrong-secret"})
        blob = json.dumps([dict(r) for r in audit.recent(limit=5)])
        assert "guessed-wrong-secret" not in blob
        assert "auth.login_failed" in blob


class TestAuditOverHttp:
    def test_denied_attempts_reach_the_log(self, client, staff_headers, owner_headers):
        client.get("/api/analytics/today", headers=staff_headers)  # 403
        rows = client.get("/api/audit?outcome=denied", headers=owner_headers).get_json()
        assert any("analytics.view" in r["action"] for r in rows)

    def test_login_is_logged(self, client, owner_headers):
        rows = client.get("/api/audit", headers=owner_headers).get_json()
        assert any(r["action"] == "auth.login" for r in rows)

    def test_clerk_cannot_read_the_audit_log(self, client, staff_headers):
        assert client.get("/api/audit", headers=staff_headers).status_code == 403

    def test_audit_response_carries_no_secrets(self, client, owner_headers):
        text = client.get("/api/audit", headers=owner_headers).get_data(as_text=True)
        assert "scrypt$" not in text
        assert TEST_PASSWORDS["owner"] not in text
