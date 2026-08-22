"""The daily hold allowance.

Five product types a day, an hour each. The interesting cases are the edges:
what counts against the allowance, what deliberately does not, and what the
shopper is told when it runs out.
"""
import pytest

import config
import db
from services import catalog, holds, reservations


def _variants(n):
    """n variants that are in stock, each from a different product."""
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
    raise AssertionError(f"seed only offers {len(out)} in-stock product types, needed {n}")


def _hold(variant, customer, quantity=1):
    holds.check(customer["id"], variant["id"])
    return reservations.create(variant["id"], customer["id"], quantity)


class TestDailyAllowance:
    def test_five_types_are_allowed(self, a_customer):
        for variant in _variants(5):
            _hold(variant, a_customer)
        assert holds.quota(a_customer["id"])["used"] == 5
        assert holds.quota(a_customer["id"])["remaining"] == 0

    def test_the_sixth_type_is_refused(self, a_customer):
        picks = _variants(6)
        for variant in picks[:5]:
            _hold(variant, a_customer)

        with pytest.raises(holds.HoldLimitReached) as caught:
            _hold(picks[5], a_customer)

        assert caught.value.quota["used"] == 5
        assert caught.value.quota["limit"] == 5

    def test_reholding_the_same_type_is_free(self, a_customer):
        """The allowance is per item type, so the same rice twice is one type."""
        picks = _variants(5)
        for variant in picks:
            _hold(variant, a_customer)

        # Full up -- but this product is already on today's list.
        again = reservations.create(picks[0]["id"], a_customer["id"], 1)
        assert again["status"] == "pending"
        assert holds.quota(a_customer["id"])["used"] == 5

    def test_quantity_does_not_consume_allowance(self, a_customer):
        """Five kilos of one rice is one shopping decision, not five."""
        variant = _variants(1)[0]
        _hold(variant, a_customer, quantity=3)
        assert holds.quota(a_customer["id"])["used"] == 1

    def test_cancelling_does_not_refund_the_slot(self, a_customer):
        """Otherwise the cap is avoidable by holding and cancelling in a loop."""
        picks = _variants(5)
        made = [_hold(v, a_customer) for v in picks]
        for row in made:
            reservations.cancel(row["id"])

        assert holds.quota(a_customer["id"])["used"] == 5
        with pytest.raises(holds.HoldLimitReached):
            _hold(_variants(6)[5], a_customer)

    def test_another_shopper_has_their_own_allowance(self, a_customer):
        from services import customers
        other = customers.find_or_create("Second Shopper", phone="9000000001")
        for variant in _variants(5):
            _hold(variant, a_customer)

        assert holds.quota(a_customer["id"])["remaining"] == 0
        assert holds.quota(other["id"])["remaining"] == 5


def _fill_day(customer, variants, days_ago=0):
    """A full day's worth of holds, optionally backdated.

    The expiry moves with the creation date, so an old day's holds lapse and
    give their stock back the way real ones would -- otherwise repeatedly
    filling the same five products just runs the shelf empty.
    """
    for variant in variants:
        reservations.create(variant["id"], customer["id"], 1)
    if days_ago:
        db.execute(
            """UPDATE reservations
               SET created_at = datetime('now', ?), expires_at = datetime('now', ?)
               WHERE customer_id = ? AND date(created_at) = date('now')""",
            (f"-{days_ago} days", f"-{days_ago} days", customer["id"]),
        )
        reservations.expire_due()


class TestRepeatWarning:
    """Three days straight, not three days out of a window."""

    def test_one_full_day_says_nothing(self, a_customer):
        _fill_day(a_customer, _variants(5))
        assert holds.quota(a_customer["id"])["charges_warning"] is False

    def test_two_days_running_says_nothing_yet(self, a_customer):
        picks = _variants(5)
        _fill_day(a_customer, picks, 1)
        _fill_day(a_customer, picks)

        quota = holds.quota(a_customer["id"])
        assert quota["streak_days"] == 2
        assert quota["charges_warning"] is False

    def test_three_days_running_warns_about_charges(self, a_customer):
        picks = _variants(5)
        for days_ago in (2, 1):
            _fill_day(a_customer, picks, days_ago)
        _fill_day(a_customer, picks)

        quota = holds.quota(a_customer["id"])
        assert quota["streak_days"] == 3
        assert quota["charges_warning"] is True
        assert "3 days in a row" in quota["charges_message"]

    def test_a_quiet_day_breaks_the_run(self, a_customer):
        """Monday and Wednesday but not Tuesday is shopping, not storage."""
        picks = _variants(5)
        for days_ago in (4, 3, 1):      # nothing on day 2
            _fill_day(a_customer, picks, days_ago)
        _fill_day(a_customer, picks)

        quota = holds.quota(a_customer["id"])
        assert quota["streak_days"] == 2
        assert quota["charges_warning"] is False

    def test_a_run_ending_yesterday_still_counts(self, a_customer):
        """So the warning can appear before the shopper spends day four."""
        picks = _variants(5)
        for days_ago in (3, 2, 1):
            _fill_day(a_customer, picks, days_ago)

        quota = holds.quota(a_customer["id"])
        assert quota["used"] == 0           # nothing held today yet
        assert quota["streak_days"] == 3
        assert quota["charges_warning"] is True

    def test_a_stale_run_is_not_live(self, a_customer):
        """Three days straight last month is not a habit today."""
        picks = _variants(5)
        for days_ago in (12, 11, 10):
            _fill_day(a_customer, picks, days_ago)

        quota = holds.quota(a_customer["id"])
        assert quota["streak_days"] == 0
        assert quota["charges_warning"] is False


class TestHoldPass:
    def test_a_pass_extends_the_day(self, a_customer):
        picks = _variants(6)
        for variant in picks[:5]:
            _hold(variant, a_customer)
        with pytest.raises(holds.HoldLimitReached):
            _hold(picks[5], a_customer)

        holds.grant_pass(a_customer["id"], "demo")

        quota = holds.quota(a_customer["id"])
        assert quota["limit"] == 5 + config.HOLD_PASS_EXTRA_TYPES
        assert quota["remaining"] == config.HOLD_PASS_EXTRA_TYPES
        assert _hold(picks[5], a_customer)["status"] == "pending"

    def test_a_pass_does_not_silence_the_charges_warning(self, a_customer):
        """Paying for today does not un-say that this is becoming a habit."""
        picks = _variants(5)
        for days_ago in (2, 1):
            _fill_day(a_customer, picks, days_ago)
        _fill_day(a_customer, picks)
        holds.grant_pass(a_customer["id"], "demo")

        assert holds.quota(a_customer["id"])["charges_warning"] is True


class TestOverTheApi:
    def test_the_cap_answers_429_with_the_quota(self, client, a_customer):
        picks = _variants(6)
        for variant in picks[:5]:
            reservations.create(variant["id"], a_customer["id"], 1)

        res = client.post("/api/reservations", json={
            "variant_id": picks[5]["id"], "customer_id": a_customer["id"], "quantity": 1,
        })
        assert res.status_code == 429
        body = res.get_json()
        assert body["reason"] == "hold_limit"
        assert body["quota"]["remaining"] == 0

    def test_staff_are_not_rationed(self, client, a_customer, staff_headers):
        """A hold placed at the counter is the store's own work."""
        picks = _variants(6)
        for variant in picks[:5]:
            reservations.create(variant["id"], a_customer["id"], 1)

        res = client.post("/api/reservations", headers=staff_headers, json={
            "variant_id": picks[5]["id"], "customer_id": a_customer["id"], "quantity": 1,
        })
        assert res.status_code == 201

    def test_quota_endpoint_reports_the_day(self, client, a_customer):
        res = client.get(f"/api/customers/{a_customer['id']}/hold-quota")
        assert res.status_code == 200
        body = res.get_json()
        assert body["limit"] == 5
        assert body["hold_minutes"] == 60

    def test_buying_a_pass_reopens_holds(self, client, a_customer):
        picks = _variants(6)
        for variant in picks[:5]:
            reservations.create(variant["id"], a_customer["id"], 1)

        bought = client.post(f"/api/customers/{a_customer['id']}/hold-pass", json={})
        assert bought.status_code == 201
        assert bought.get_json()["remaining"] == config.HOLD_PASS_EXTRA_TYPES

        res = client.post("/api/reservations", json={
            "variant_id": picks[5]["id"], "customer_id": a_customer["id"], "quantity": 1,
        })
        assert res.status_code == 201

    def test_the_pass_qr_renders(self, client):
        res = client.get("/api/holds/pass.qr.svg")
        assert res.status_code == 200
        assert res.mimetype == "image/svg+xml"
        assert b"<svg" in res.data

    def test_the_qr_follows_the_configured_payload(self, client, monkeypatch):
        """Two different payment strings must not produce the same code."""
        monkeypatch.setattr(config, "HOLD_PASS_QR_PAYLOAD", "upi://pay?pa=one@bank")
        first = client.get("/api/holds/pass.qr.svg").data
        monkeypatch.setattr(config, "HOLD_PASS_QR_PAYLOAD", "upi://pay?pa=two@bank")
        assert client.get("/api/holds/pass.qr.svg").data != first

    def test_the_demo_label_tracks_the_placeholder(self, client, a_customer, monkeypatch):
        """Setting a real payment string must take the DEMO badge off with it."""
        monkeypatch.setattr(config, "HOLD_PASS_QR_IS_DEMO", False)
        live = client.get(f"/api/customers/{a_customer['id']}/hold-quota").get_json()
        assert live["pass_qr_is_demo"] is False

        monkeypatch.setattr(config, "HOLD_PASS_QR_IS_DEMO", True)
        placeholder = client.get(f"/api/customers/{a_customer['id']}/hold-quota").get_json()
        assert placeholder["pass_qr_is_demo"] is True

    def test_config_publishes_the_limit(self, client):
        body = client.get("/api/config").get_json()
        assert body["hold_types_per_day"] == 5
        assert body["reservation_minutes"] == 60
