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


class TestRefundOnCancelledBuyNow:
    def test_cancelling_refunds_the_payment(self, a_variant, a_customer):
        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 2)
        order = db.query_one(
            "SELECT * FROM orders WHERE reservation_id = ?", (bought["id"],))
        assert order["refunded_at"] is None

        reservations.cancel(bought["id"], actor=None)

        order = db.query_one("SELECT * FROM orders WHERE id = ?", (order["id"],))
        assert order["refunded_at"] is not None
        payment = db.query_one(
            "SELECT * FROM payments WHERE order_id = ?", (order["id"],))
        assert payment["status"] == "refunded"
        refund = db.query_one(
            "SELECT * FROM refunds WHERE order_id = ?", (order["id"],))
        assert refund is not None
        assert refund["amount"] == payment["amount"] == order["total"]
        assert "cancelled" in refund["reason"]

    def test_rejecting_refunds_the_payment_too(self, a_variant, a_customer, owner):
        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        reservations.reject(bought["id"], actor=owner)

        payment = db.query_one(
            """SELECT p.* FROM payments p JOIN orders o ON o.id = p.order_id
               WHERE o.reservation_id = ?""", (bought["id"],))
        assert payment["status"] == "refunded"

    def test_an_unpaid_hold_is_not_refunded_because_nothing_was_charged(self, a_variant, a_customer):
        """Regression: cancelling a normal (never-paid) hold must not touch
        orders/payments/refunds at all -- there was never a sale to undo."""
        held = reservations.create(a_variant["id"], a_customer["id"], 1)
        reservations.cancel(held["id"])

        assert not db.query("SELECT 1 FROM orders WHERE reservation_id = ?", (held["id"],))
        assert not db.query("SELECT 1 FROM refunds")

    def test_a_completed_pickup_has_nothing_to_refund_on_a_later_cancel_attempt(self, a_variant, a_customer, owner):
        """Once picked up, the reservation is no longer open, so cancel/reject
        are refused before any refund logic even runs (belt and braces:
        _write_refund also no-ops if it somehow found a completed order)."""
        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        reservations.complete(bought["id"], actor=owner)

        with pytest.raises(ReservationError):
            reservations.cancel(bought["id"])

    def test_refunded_revenue_drops_out_of_todays_sales(self, a_variant, a_customer):
        from services import analytics

        before = analytics.today()["revenue"]
        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        after_purchase = analytics.today()["revenue"]
        assert after_purchase == round(before + a_variant["price"], 2)

        reservations.cancel(bought["id"])
        after_refund = analytics.today()["revenue"]
        assert after_refund == before

    def test_refunded_orders_drop_out_of_top_products_too(self, a_variant, a_customer):
        """The seed data may already carry other, unrelated sales for this
        same SKU, so the assertion is on the revenue this purchase added
        being gone again -- not on the SKU vanishing from the list outright."""
        from services import analytics

        def revenue_for(sku):
            row = next((p for p in analytics.top_products(limit=50) if p["sku"] == sku), None)
            return row["revenue"] if row else 0

        before = revenue_for(a_variant["sku"])
        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 1)
        assert revenue_for(a_variant["sku"]) == round(before + a_variant["price"], 2)

        reservations.cancel(bought["id"])
        assert revenue_for(a_variant["sku"]) == before


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


class TestRefundHistory:
    def test_lists_a_refund_with_its_context(self, a_variant, a_customer):
        from services import analytics

        bought = reservations.buy_now(a_variant["id"], a_customer["id"], 2)
        reservations.cancel(bought["id"])

        report = analytics.refunds()
        assert report["count"] == 1
        assert report["total"] == a_variant["price"] * 2

        row = report["items"][0]
        assert row["reservation_code"] == bought["code"]
        assert row["customer_name"] == a_customer["name"]
        assert row["sku"] == a_variant["sku"]
        assert row["quantity"] == 2
        assert row["amount"] == a_variant["price"] * 2
        assert "cancelled" in row["reason"]

    def test_total_and_count_add_up_across_several_refunds(self, a_customer):
        from services import analytics, catalog

        picks, seen = [], set()
        for product in catalog.list_products():
            if product["id"] in seen:
                continue
            full = catalog.get_product(product["id"])
            for variant in full["variants"]:
                if variant["stock"]["available"] > 0:
                    picks.append(variant)
                    seen.add(product["id"])
                    break
            if len(picks) == 3:
                break

        expected_total = 0
        for variant in picks:
            bought = reservations.buy_now(variant["id"], a_customer["id"], 1)
            reservations.cancel(bought["id"])
            expected_total += variant["price"]

        report = analytics.refunds()
        assert report["count"] == len(picks)
        assert report["total"] == round(expected_total, 2)

    def test_an_unpaid_cancelled_hold_never_shows_up(self, a_variant, a_customer):
        from services import analytics

        held = reservations.create(a_variant["id"], a_customer["id"], 1)
        reservations.cancel(held["id"])

        assert analytics.refunds()["count"] == 0

    def test_owner_and_manager_can_view_the_report(self, client, owner_headers, manager_headers):
        for headers in (owner_headers, manager_headers):
            res = client.get("/api/analytics/refunds", headers=headers)
            assert res.status_code == 200
            body = res.get_json()
            assert "items" in body and "total" in body and "count" in body

    def test_plain_staff_cannot_view_the_report(self, client, staff_headers):
        res = client.get("/api/analytics/refunds", headers=staff_headers)
        assert res.status_code == 403

    def test_anonymous_cannot_view_the_report(self, client):
        res = client.get("/api/analytics/refunds")
        assert res.status_code == 401
