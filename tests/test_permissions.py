"""The permission matrix itself, checked directly rather than through HTTP."""
import pytest

from services.security import (MANAGER, OWNER, PERMISSIONS, ROLES, STAFF, SYSTEM,
                               NotAuthenticated, PermissionDenied, can,
                               is_valid_role, matrix, permissions_for, require)


class TestMatrixShape:
    def test_every_permission_names_at_least_one_role(self):
        for permission, roles in PERMISSIONS.items():
            assert roles, f"{permission} is grantable to nobody"

    def test_every_permission_uses_known_roles_only(self):
        for permission, roles in PERMISSIONS.items():
            unknown = roles - set(ROLES)
            assert not unknown, f"{permission} references unknown role(s) {unknown}"

    def test_owner_holds_every_permission(self):
        """An owner locked out of part of their own store cannot fix it."""
        missing = [p for p, roles in PERMISSIONS.items() if OWNER not in roles]
        assert not missing, f"owner is missing {missing}"

    def test_roles_are_ordered_by_privilege(self):
        """Staff must never hold something a manager lacks."""
        for permission, roles in PERMISSIONS.items():
            if STAFF in roles:
                assert MANAGER in roles, f"staff outrank manager on {permission}"

    def test_matrix_is_serialisable(self):
        table = matrix()
        assert isinstance(table, dict)
        assert all(isinstance(v, list) for v in table.values())


class TestDestructivePermissionsAreOwnerOnly:
    """The operations that lose data or money stop at the owner."""

    @pytest.mark.parametrize("permission", [
        "product.delete", "order.void", "customer.delete",
        "settings.edit", "staff.create", "staff.edit", "staff.disable",
        "refund.approve", "demo.reset",
    ])
    def test_owner_only(self, permission):
        assert PERMISSIONS[permission] == {OWNER}


class TestCan:
    def test_role_holds_its_permissions(self, clerk):
        assert can(clerk, "inventory.adjust")
        assert can(clerk, "reservation.accept")

    def test_role_lacks_others(self, clerk):
        assert not can(clerk, "inventory.stocktake")
        assert not can(clerk, "reservation.reject")
        assert not can(clerk, "analytics.view")
        assert not can(clerk, "staff.create")

    def test_manager_sits_between(self, manager):
        assert can(manager, "inventory.stocktake")
        assert can(manager, "reservation.reject")
        assert can(manager, "analytics.view")
        assert not can(manager, "staff.create")
        assert not can(manager, "demo.reset")

    def test_owner_can_everything(self, owner):
        assert all(can(owner, p) for p in PERMISSIONS)

    def test_anonymous_can_nothing(self):
        assert not any(can(None, p) for p in PERMISSIONS)
        assert not any(can({}, p) for p in PERMISSIONS)

    def test_disabled_account_can_nothing(self, disabled_user):
        assert disabled_user["status"] == "disabled"
        assert not any(can(disabled_user, p) for p in PERMISSIONS)

    def test_unknown_role_can_nothing(self):
        impostor = {"role": "superuser", "status": "active"}
        assert not any(can(impostor, p) for p in PERMISSIONS)

    def test_unknown_permission_raises_rather_than_silently_allowing(self, owner):
        """A typo'd permission must fail loudly, not default to permitted."""
        with pytest.raises(KeyError):
            can(owner, "inventory.destroy_everything")

    def test_system_actor_is_allowed(self):
        assert can(SYSTEM, "reservation.reject")


class TestRequire:
    def test_passes_when_allowed(self, owner):
        assert require(owner, "staff.create") is True

    def test_raises_permission_denied_when_signed_in_but_not_allowed(self, clerk):
        with pytest.raises(PermissionDenied) as err:
            require(clerk, "staff.create")
        assert err.value.permission == "staff.create"

    def test_raises_not_authenticated_when_anonymous(self):
        with pytest.raises(NotAuthenticated):
            require(None, "inventory.view")

    def test_disabled_reads_as_unauthenticated_not_forbidden(self, disabled_user):
        """A switched-off account should not hint at what it used to reach."""
        with pytest.raises(NotAuthenticated):
            require(disabled_user, "inventory.view")

    def test_denial_message_avoids_leaking_internals(self, clerk):
        with pytest.raises(PermissionDenied) as err:
            require(clerk, "settings.edit")
        message = str(err.value)
        assert "password" not in message.lower()
        assert "hash" not in message.lower()


class TestPermissionsFor:
    def test_lists_only_that_role(self):
        for role in ROLES:
            for permission in permissions_for(role):
                assert role in PERMISSIONS[permission]

    def test_owner_list_is_the_longest(self):
        assert len(permissions_for(OWNER)) > len(permissions_for(MANAGER))
        assert len(permissions_for(MANAGER)) > len(permissions_for(STAFF))

    def test_valid_roles(self):
        assert all(is_valid_role(r) for r in ROLES)
        assert not is_valid_role("root")
        assert not is_valid_role(None)
