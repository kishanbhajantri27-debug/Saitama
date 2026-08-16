"""Behaviour that worked before this change and must still work.

There was no suite when the permission work started, so this file pins down the
existing behaviour: stock arithmetic, the reservation lifecycle, search and
freshness. If the authorization work broke something, it fails here.
"""
import pytest

from services import catalog, inventory, reservations
from services.security import SYSTEM


class TestStockArithmetic:
    def test_available_is_on_hand_minus_reserved(self, a_variant):
        s = a_variant["stock"]
        assert s["available"] == s["on_hand"] - s["reserved"]

    def test_the_hero_product_matches_the_demo_script(self):
        """4 available, the number the walkthrough is written around."""
        s = catalog.find_by_code("NIK-AM-092")["stock"]
        assert s["on_hand"] == 5
        assert s["reserved"] == 1
        assert s["available"] == 4
        assert s["status"] == "available"

    def test_status_bands(self):
        assert inventory.stock_status(0) == "out"
        assert inventory.stock_status(1) == "limited"
        assert inventory.stock_status(3) == "limited"
        assert inventory.stock_status(4) == "available"

    def test_freshness_bands(self):
        assert inventory.freshness("2099-01-01 00:00:00")["level"] == "fresh"
        assert inventory.freshness(None)["stale"] is True

    def test_cannot_count_away_reserved_stock(self, owner, a_variant):
        with pytest.raises(ValueError, match="reserved"):
            inventory.change_stock(a_variant["id"], "adjust", 0, actor=owner)

    def test_cannot_remove_more_than_on_hand(self, owner, a_variant):
        with pytest.raises(ValueError, match="cannot remove"):
            inventory.change_stock(a_variant["id"], "remove", 999, actor=owner)


class TestReservationLifecycle:
    """The section 17 walkthrough, start to finish."""

    def test_full_flow_moves_the_numbers_correctly(self, owner, a_variant, a_customer):
        vid = a_variant["id"]
        start = inventory.describe(inventory.get(vid))

        r = reservations.create(vid, a_customer["id"], 1)
        after_reserve = inventory.describe(inventory.get(vid))
        assert after_reserve["on_hand"] == start["on_hand"], "reserving must not move stock"
        assert after_reserve["available"] == start["available"] - 1

        reservations.accept(r["id"], actor=owner)
        assert inventory.describe(inventory.get(vid)) == after_reserve, "accept moves nothing"

        reservations.mark_ready(r["id"], actor=owner)
        assert inventory.describe(inventory.get(vid)) == after_reserve, "ready moves nothing"

        reservations.complete(r["id"], actor=owner)
        done = inventory.describe(inventory.get(vid))
        assert done["on_hand"] == start["on_hand"] - 1
        assert done["reserved"] == start["reserved"]
        assert reservations.get(r["id"])["status"] == "completed"

    def test_rejecting_releases_the_hold(self, owner, a_variant, a_customer):
        vid = a_variant["id"]
        before = inventory.describe(inventory.get(vid))["available"]
        r = reservations.create(vid, a_customer["id"], 1)
        assert inventory.describe(inventory.get(vid))["available"] == before - 1
        reservations.reject(r["id"], actor=owner)
        assert inventory.describe(inventory.get(vid))["available"] == before

    def test_cannot_reserve_more_than_available(self, a_variant, a_customer):
        with pytest.raises(reservations.ReservationError):
            reservations.create(a_variant["id"], a_customer["id"], 999)

    def test_cannot_reserve_out_of_stock(self, a_customer):
        out = catalog.find_by_code("SAM-25W")
        assert out["stock"]["available"] == 0
        with pytest.raises(reservations.ReservationError, match="out of stock"):
            reservations.create(out["id"], a_customer["id"], 1)

    def test_illegal_transitions_are_refused(self, owner, a_variant, a_customer):
        r = reservations.create(a_variant["id"], a_customer["id"], 1)
        with pytest.raises(reservations.ReservationError):
            reservations.complete(r["id"], actor=owner)   # not accepted yet
        reservations.accept(r["id"], actor=owner)
        with pytest.raises(reservations.ReservationError):
            reservations.accept(r["id"], actor=owner)     # twice
        reservations.complete(r["id"], actor=owner)
        with pytest.raises(reservations.ReservationError):
            reservations.complete(r["id"], actor=owner)   # twice

    def test_completing_writes_a_sale(self, owner, a_variant, a_customer):
        import db
        before = db.query_one("SELECT COUNT(*) AS n FROM orders")["n"]
        r = reservations.create(a_variant["id"], a_customer["id"], 1)
        reservations.accept(r["id"], actor=owner)
        reservations.complete(r["id"], actor=owner)
        assert db.query_one("SELECT COUNT(*) AS n FROM orders")["n"] == before + 1

    def test_expiry_releases_holds(self, a_variant, a_customer):
        vid = a_variant["id"]
        before = inventory.describe(inventory.get(vid))["available"]
        r = reservations.create(vid, a_customer["id"], 1, minutes=-1)  # already expired
        reservations.expire_due()
        assert reservations.get(r["id"])["status"] == "expired"
        assert inventory.describe(inventory.get(vid))["available"] == before

    def test_expiry_runs_without_a_signed_in_user(self, a_variant, a_customer):
        """Unattended work uses the system actor, not a person's credentials."""
        reservations.create(a_variant["id"], a_customer["id"], 1, minutes=-1)
        assert reservations.expire_due() >= 1


class TestSearch:
    @pytest.mark.parametrize("query,expected", [
        ("Nike shoes", "Nike Air Max"),
        ("Samsung charger", "Samsung 25W Charger"),
        ("Black shirt", "Cotton T-Shirt"),
        ("Notebook", "Ruled Notebook"),
        ("Bluetooth headphones", "Bluetooth Headphones"),
        ("black jeans", "Levi's 511 Jeans"),
    ])
    def test_sample_queries_still_work(self, query, expected):
        names = [p["name"] for p in catalog.list_products(search=query)]
        assert expected in names, f"{query!r} should find {expected}"

    def test_search_by_sku(self):
        assert catalog.list_products(search="NIK-AM-092")[0]["name"] == "Nike Air Max"

    def test_search_by_barcode(self):
        assert catalog.list_products(search="8901234500025")[0]["name"] == "Nike Air Max"

    def test_lookup_by_code(self):
        assert catalog.find_by_code("8901234500025")["sku"] == "NIK-AM-092"
        assert catalog.find_by_code("nik-am-092") is not None  # case-insensitive
        assert catalog.find_by_code("nonsense") is None

    def test_filters(self):
        for p in catalog.list_products(category="Footwear"):
            assert p["category"] == "Footwear"
        for p in catalog.list_products(status="out"):
            assert p["available"] == 0

    def test_check_many_finds_everything(self):
        result = catalog.check_many(["Nike shoes", "Black jeans", "Backpack"])
        assert result["all_available"] is True


class TestMovementTimeline:
    def test_pickup_reports_stock_not_availability(self, owner, a_variant, a_customer):
        """on-hand and the hold fall together, so availability does not move."""
        r = reservations.create(a_variant["id"], a_customer["id"], 1)
        reservations.accept(r["id"], actor=owner)
        reservations.complete(r["id"], actor=owner)
        pickup = [m for m in inventory.movements(variant_id=a_variant["id"])
                  if m["kind"] == "PICKUP"][0]
        assert pickup["on_hand_delta"] == -1
        assert pickup["available_delta"] == 0
        assert pickup["effect"] == "-1 stock"

    def test_reservation_reports_availability_not_stock(self, a_variant, a_customer):
        reservations.create(a_variant["id"], a_customer["id"], 1)
        created = [m for m in inventory.movements(variant_id=a_variant["id"])
                   if m["kind"] == "RESERVATION"][0]
        assert created["on_hand_delta"] == 0
        assert created["available_delta"] == -1
        assert created["effect"] == "-1 available"

    def test_every_movement_has_a_human_label(self, a_variant):
        for m in inventory.movements(limit=50):
            assert m["label"] and m["label"] != m["kind"].lower()


class TestSeedAndReset:
    def test_reset_restores_the_opening_state(self, owner, a_variant):
        import db
        inventory.change_stock(a_variant["id"], "add", 50, actor=owner)
        assert inventory.get(a_variant["id"])["on_hand"] > 5
        db.reset()
        import seed
        seed.run(force=True)
        assert catalog.find_by_code("NIK-AM-092")["stock"]["on_hand"] == 5

    def test_seed_is_idempotent(self):
        import seed
        assert seed.run() is False, "second run on a seeded db should do nothing"

    def test_every_seeded_staff_account_can_be_looked_up(self):
        from services import staff
        for username in ("owner", "manager", "staff", "exstaff"):
            assert staff.get_by_username(username) is not None
