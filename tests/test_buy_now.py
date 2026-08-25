"""Buy it now: paid immediately, picked up later, no accept step.

A hold reserves stock on a promise; this is a sale that already happened, so
it should behave like one -- ready for pickup from the moment it is created,
paid exactly once even though the customer eventually walks in and staff
tap "Complete pickup" too, and never quietly expiring the way an unpaid
hold does.
"""
import pytest

import db
from services import holds, reservations
from services.reservations import ReservationError


def _stock(variant_id):
    return db.query_one(
        "SELECT * FROM inventory WHERE variant_id = ?", (variant_id,))


class TestBuyNowCreatesAPrepaidSale:
    def test_starts_ready_for_pickup_and_never_expires(self, a_variant, a_customer):
        result = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        assert result["status"] == "ready_for_pickup"
        assert result["prepaid"] == 1
        assert result["expires_at"] is None
        assert result["expires_in_minutes"] is None
        assert result["is_open"] is True

    def test_reserves_stock_like_a_hold(self, a_variant, a_customer):
        before = _stock(a_variant["id"])
        reservations.buy_now(a_variant["id"], a_customer["id"], 2)
        after = _stock(a_variant["id"])
        assert after["reserved"] == before["reserved"] + 2
        assert after["on_hand"] == before["on_hand"]  # nothing leaves the shelf yet

    def test_writes_the_sale_immediately(self, a_variant, a_customer):
        result = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        orders = db.query(
            "SELECT * FROM orders WHERE reservation_id = ?", (result["id"],))
        assert len(orders) == 1
        assert orders[0]["channel"] == "reservation-pickup"
        payments = db.query(
            "SELECT * FROM payments WHERE order_id = ?", (orders[0]["id"],))
        assert len(payments) == 1
        assert payments[0]["status"] == "captured"

    def test_refuses_more_than_is_available(self, a_variant, a_customer):
        available = a_variant["stock"]["available"]
        with pytest.raises(ReservationError):
            reservations.buy_now(a_variant["id"], a_customer["id"], available + 1)

    def test_does_not_count_against_the_hold_allowance(self, a_variant, a_customer):
        reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        assert holds.quota(a_customer["id"])["used"] == 0

    def test_bypasses_a_used_up_hold_allowance(self, a_customer):
        """The whole point: rationing free holds must not block a paid sale."""
        from services import catalog

        def variants(n):
            out, seen = [], set()
            for product in catalog.list_products():
                if product["id"] in seen:
                    continue
                full = catalog.get_product(product["id"])
                for variant in full["variants"]:
                    if variant["stock"]["available"] > 0:
                        out.append(variant)
                        seen.add(product["id"])
                        break
                if len(out) == n:
                    return out
            raise AssertionError("seed does not offer enough in-stock product types")

        picks = variants(6)
        for variant in picks[:5]:
            holds.check(a_customer["id"], variant["id"])
            reservations.create(variant["id"], a_customer["id"], 1)
        with pytest.raises(holds.HoldLimitReached):
            holds.check(a_customer["id"], picks[5]["id"])

        result = reservations.buy_now(picks[5]["id"], a_customer["id"], 1)
        assert result["status"] == "ready_for_pickup"


class TestPickupAfterBuyNow:
    def test_complete_consumes_stock_without_a_second_sale(self, a_variant, a_customer, owner):
        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        before = _stock(a_variant["id"])

        completed = reservations.complete(bought["id"], actor=owner)

        after = _stock(a_variant["id"])
        assert completed["status"] == "completed"
        assert after["on_hand"] == before["on_hand"] - 1
        assert after["reserved"] == before["reserved"] - 1
        orders = db.query(
            "SELECT * FROM orders WHERE reservation_id = ?", (bought["id"],))
        assert len(orders) == 1  # written once at buy_now, not again at pickup

    def test_a_normal_reservation_still_gets_its_sale_at_pickup(self, a_variant, a_customer, owner):
        """The prepaid guard must not disturb the unpaid-hold path."""
        held = reservations.create(a_variant["id"], a_customer["id"], 1)
        reservations.accept(held["id"], actor=owner)
        completed = reservations.complete(held["id"], actor=owner)
        assert completed["status"] == "completed"
        orders = db.query(
            "SELECT * FROM orders WHERE reservation_id = ?", (held["id"],))
        assert len(orders) == 1

    def test_rejecting_a_bought_item_still_releases_the_stock(self, a_variant, a_customer, owner):
        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        before = _stock(a_variant["id"])
        reservations.reject(bought["id"], actor=owner)
        after = _stock(a_variant["id"])
        assert after["reserved"] == before["reserved"] - 1


class TestBuyNowOverTheApi:
    def test_creates_a_ready_reservation(self, client, a_variant, a_customer):
        res = client.post("/api/reservations/buy-now", json={
            "variant_id": a_variant["id"], "customer_id": a_customer["id"], "quantity": 1,
        })
        assert res.status_code == 201
        body = res.get_json()
        assert body["status"] == "ready_for_pickup"
        assert body["prepaid"] == 1

    def test_is_not_rationed_by_the_hold_limit(self, client, a_customer):
        from services import catalog

        def variants(n):
            out, seen = [], set()
            for product in catalog.list_products():
                if product["id"] in seen:
                    continue
                full = catalog.get_product(product["id"])
                for variant in full["variants"]:
                    if variant["stock"]["available"] > 0:
                        out.append(variant)
                        seen.add(product["id"])
                        break
                if len(out) == n:
                    return out
            raise AssertionError("seed does not offer enough in-stock product types")

        picks = variants(6)
        for variant in picks[:5]:
            res = client.post("/api/reservations", json={
                "variant_id": variant["id"], "customer_id": a_customer["id"], "quantity": 1,
            })
            assert res.status_code == 201

        blocked = client.post("/api/reservations", json={
            "variant_id": picks[5]["id"], "customer_id": a_customer["id"], "quantity": 1,
        })
        assert blocked.status_code == 429

        bought = client.post("/api/reservations/buy-now", json={
            "variant_id": picks[5]["id"], "customer_id": a_customer["id"], "quantity": 1,
        })
        assert bought.status_code == 201

    def test_requires_a_variant(self, client, a_customer):
        res = client.post("/api/reservations/buy-now", json={
            "customer_id": a_customer["id"], "quantity": 1,
        })
        assert res.status_code == 400
