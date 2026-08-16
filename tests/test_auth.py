"""Authentication: passwords, sessions, disabled and deleted accounts."""
import pytest

from conftest import TEST_PASSWORDS

from services import staff
from services.security import NotAuthenticated, PermissionDenied


class TestPasswordHashing:
    def test_hash_is_not_the_password(self):
        digest = staff.hash_password("hunter2")
        assert "hunter2" not in digest

    def test_hash_is_salted_differently_each_time(self):
        """Equal passwords must not produce equal digests."""
        assert staff.hash_password("same") != staff.hash_password("same")

    def test_verify_accepts_the_right_password(self):
        digest = staff.hash_password("correct horse")
        assert staff.verify_password("correct horse", digest)

    def test_verify_rejects_the_wrong_one(self):
        digest = staff.hash_password("correct horse")
        assert not staff.verify_password("wrong horse", digest)
        assert not staff.verify_password("", digest)
        assert not staff.verify_password(None, digest)

    def test_verify_survives_a_corrupt_hash(self):
        """A damaged row is a failed login, never a crash."""
        for broken in ["", "garbage", "scrypt$bad", None, "md5$1$2$3$4$5"]:
            assert not staff.verify_password("anything", broken)

    def test_short_passwords_rejected(self):
        with pytest.raises(ValueError):
            staff.hash_password("ab")


class TestAuthenticate:
    def test_valid_credentials(self):
        assert staff.authenticate("owner", TEST_PASSWORDS["owner"])["role"] == "owner"

    def test_wrong_password(self):
        assert staff.authenticate("owner", "nope") is None

    def test_unknown_username(self):
        assert staff.authenticate("nobody", TEST_PASSWORDS["owner"]) is None

    def test_disabled_account_cannot_authenticate(self):
        """Right password, switched-off account: still no."""
        assert staff.authenticate("exstaff", TEST_PASSWORDS["exstaff"]) is None

    def test_username_is_case_insensitive(self):
        assert staff.authenticate("OWNER", TEST_PASSWORDS["owner"]) is not None

    def test_password_is_case_sensitive(self):
        assert staff.authenticate("owner", "OWNER123") is None

    def test_last_login_recorded(self):
        before = staff.get_by_username("owner")["last_login_at"]
        staff.authenticate("owner", TEST_PASSWORDS["owner"])
        assert staff.get_by_username("owner")["last_login_at"] != before or before is None


class TestPublicSerialisation:
    def test_password_hash_never_leaves(self, owner):
        assert "password_hash" in owner, "fixture should hold the raw row"
        assert "password_hash" not in staff.public(owner)

    def test_public_keeps_the_useful_fields(self, owner):
        out = staff.public(owner)
        assert out["username"] == "owner"
        assert out["role"] == "owner"
        assert out["status"] == "active"

    def test_list_all_never_includes_hashes(self, owner):
        for row in staff.list_all(actor=owner):
            assert "password_hash" not in row


class TestAccountLifecycle:
    def test_owner_can_create_staff(self, owner):
        created = staff.create(owner, "New Person", "newbie", "pass1234", "staff")
        assert created["username"] == "newbie"
        assert "password_hash" not in created
        assert staff.authenticate("newbie", "pass1234") is not None

    def test_manager_cannot_create_staff(self, manager):
        with pytest.raises(PermissionDenied):
            staff.create(manager, "Sneaky", "sneak", "pass1234", "owner")

    def test_clerk_cannot_create_staff(self, clerk):
        with pytest.raises(PermissionDenied):
            staff.create(clerk, "Sneaky", "sneak2", "pass1234", "staff")

    def test_duplicate_username_rejected(self, owner):
        with pytest.raises(ValueError):
            staff.create(owner, "Clash", "owner", "pass1234", "staff")

    def test_unknown_role_rejected(self, owner):
        with pytest.raises(ValueError):
            staff.create(owner, "Odd", "odd", "pass1234", "wizard")

    def test_role_change_takes_effect(self, owner, clerk):
        from services.security import can
        assert not can(clerk, "analytics.view")
        staff.set_role(owner, clerk["id"], "manager")
        assert can(staff.get(clerk["id"]), "analytics.view")

    def test_disabling_blocks_login_immediately(self, owner, clerk):
        assert staff.authenticate("staff", TEST_PASSWORDS["staff"]) is not None
        staff.set_status(owner, clerk["id"], "disabled")
        assert staff.authenticate("staff", TEST_PASSWORDS["staff"]) is None

    def test_reenabling_restores_login(self, owner, disabled_user):
        staff.set_status(owner, disabled_user["id"], "active")
        assert staff.authenticate("exstaff", TEST_PASSWORDS["exstaff"]) is not None

    def test_deleted_account_cannot_authenticate(self, owner, clerk):
        staff.delete(owner, clerk["id"])
        assert staff.authenticate("staff", TEST_PASSWORDS["staff"]) is None
        assert staff.get(clerk["id"]) is None

    def test_password_change_invalidates_the_old_one(self, owner, clerk):
        staff.set_password(owner, clerk["id"], "brand-new-pass")
        assert staff.authenticate("staff", TEST_PASSWORDS["staff"]) is None
        assert staff.authenticate("staff", "brand-new-pass") is not None

    def test_anyone_may_change_their_own_password(self, clerk):
        """No elevated permission needed for your own account."""
        staff.set_password(clerk, clerk["id"], "my-own-choice")
        assert staff.authenticate("staff", "my-own-choice") is not None

    def test_clerk_cannot_change_someone_elses_password(self, clerk, manager):
        with pytest.raises(PermissionDenied):
            staff.set_password(clerk, manager["id"], "hijacked")


class TestLastOwnerProtection:
    """A store with no active owner cannot be administered back to health."""

    def test_cannot_demote_the_only_owner(self, owner):
        with pytest.raises(ValueError, match="only active owner"):
            staff.set_role(owner, owner["id"], "staff")

    def test_cannot_disable_the_only_owner(self, owner):
        with pytest.raises(ValueError, match="only active owner"):
            staff.set_status(owner, owner["id"], "disabled")

    def test_cannot_delete_the_only_owner(self, owner):
        with pytest.raises(ValueError, match="only active owner"):
            staff.delete(owner, owner["id"])

    def test_can_demote_once_a_second_owner_exists(self, owner):
        staff.create(owner, "Second Owner", "owner2", "pass1234", "owner")
        assert staff.set_role(owner, owner["id"], "manager")["role"] == "manager"

    def test_cannot_disable_own_account(self, owner):
        staff.create(owner, "Second Owner", "owner2", "pass1234", "owner")
        with pytest.raises(ValueError, match="your own account"):
            staff.set_status(owner, owner["id"], "disabled")
