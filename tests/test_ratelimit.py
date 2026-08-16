"""Login rate limiting.

The unit tests drive a fake clock rather than sleeping, so the whole suite
stays fast and the window boundaries can be tested exactly.
"""
import pytest

from conftest import TEST_PASSWORDS
from services import ratelimit
from services.ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(clock):
    return RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120, clock=clock)


class TestSlidingWindow:
    def test_allows_attempts_below_the_limit(self, limiter):
        for _ in range(2):
            limiter.record_failure("bob")
        assert not limiter.is_limited("bob")

    def test_locks_on_reaching_the_limit(self, limiter):
        for _ in range(3):
            limiter.record_failure("bob")
        assert limiter.is_limited("bob")
        assert limiter.retry_after("bob") == 120

    def test_lockout_expires(self, limiter, clock):
        for _ in range(3):
            limiter.record_failure("bob")
        clock.advance(119)
        assert limiter.is_limited("bob")
        clock.advance(2)
        assert not limiter.is_limited("bob")

    def test_failures_age_out_of_the_window(self, limiter, clock):
        """Two mistakes an hour apart must not add up to a lockout."""
        limiter.record_failure("bob")
        limiter.record_failure("bob")
        clock.advance(61)
        limiter.record_failure("bob")
        assert not limiter.is_limited("bob")
        assert limiter.failure_count("bob") == 1

    def test_success_clears_the_counter(self, limiter):
        limiter.record_failure("bob")
        limiter.record_failure("bob")
        limiter.record_success("bob")
        assert limiter.failure_count("bob") == 0

    def test_serving_a_lockout_clears_the_slate(self, limiter, clock):
        """After waiting it out, one more mistake must not re-lock instantly."""
        for _ in range(3):
            limiter.record_failure("bob")
        clock.advance(121)
        assert not limiter.is_limited("bob")
        limiter.record_failure("bob")
        assert not limiter.is_limited("bob")

    def test_keys_are_independent(self, limiter):
        for _ in range(3):
            limiter.record_failure("bob")
        assert limiter.is_limited("bob")
        assert not limiter.is_limited("alice")

    def test_empty_keys_are_ignored(self, limiter):
        assert limiter.record_failure("") == 0
        assert limiter.retry_after(None) == 0

    def test_retry_after_never_reports_zero_while_locked(self, limiter, clock):
        for _ in range(3):
            limiter.record_failure("bob")
        clock.advance(119.7)
        assert limiter.retry_after("bob") >= 1


class TestLoginRateLimiting:
    """Over HTTP, against the real limiter."""

    def wrong(self, client, username="owner"):
        return client.post("/api/session/staff",
                           json={"username": username, "password": "definitely-wrong"})

    def test_repeated_failures_eventually_return_429(self, client):
        for _ in range(5):
            assert self.wrong(client).status_code == 401
        res = self.wrong(client)
        assert res.status_code == 429
        assert res.headers.get("Retry-After")
        assert res.get_json()["retry_after"] > 0

    def test_the_correct_password_is_refused_while_locked(self, client):
        """Otherwise the limit would be trivially bypassed by guessing on."""
        for _ in range(5):
            self.wrong(client)
        res = client.post("/api/session/staff",
                          json={"username": "owner", "password": TEST_PASSWORDS["owner"]})
        assert res.status_code == 429

    def test_a_good_password_before_the_limit_clears_it(self, client):
        for _ in range(3):
            self.wrong(client)
        ok = client.post("/api/session/staff",
                         json={"username": "owner", "password": TEST_PASSWORDS["owner"]})
        assert ok.status_code == 200
        # Counter cleared, so the next few mistakes must not lock immediately.
        for _ in range(3):
            assert self.wrong(client).status_code == 401

    def test_unknown_usernames_are_limited_too(self, client):
        """Limiting only real accounts would reveal which ones exist."""
        for _ in range(5):
            assert self.wrong(client, "no-such-person").status_code == 401
        assert self.wrong(client, "no-such-person").status_code == 429

    def test_a_real_and_a_fake_username_behave_alike(self, client):
        real = [self.wrong(client, "owner").status_code for _ in range(6)]
        ratelimit.reset_all()
        fake = [self.wrong(client, "ghost-account").status_code for _ in range(6)]
        assert real == fake, "lockout behaviour must not distinguish real accounts"

    def test_one_account_lockout_does_not_block_another(self, client):
        for _ in range(5):
            self.wrong(client, "owner")
        assert self.wrong(client, "owner").status_code == 429
        res = client.post("/api/session/staff",
                          json={"username": "manager", "password": TEST_PASSWORDS["manager"]})
        assert res.status_code == 200, "a second account must still be able to sign in"

    def test_spraying_many_usernames_trips_the_address_limit(self, client):
        """Each username stays under its own limit, but the address does not."""
        for i in range(20):
            self.wrong(client, f"user{i}")
        res = client.post("/api/session/staff",
                          json={"username": "fresh-name", "password": "whatever"})
        assert res.status_code == 429

    def test_rate_limited_attempts_are_audited(self, client, owner_headers):
        for _ in range(6):
            self.wrong(client, "manager")
        rows = client.get("/api/audit?outcome=denied", headers=owner_headers).get_json()
        assert any(r["action"] == "auth.rate_limited" for r in rows)

    def test_the_lockout_response_leaks_nothing(self, client):
        for _ in range(6):
            self.wrong(client)
        text = self.wrong(client).get_data(as_text=True)
        assert "definitely-wrong" not in text
        assert "scrypt$" not in text
        assert "owner" not in text.lower() or "username" not in text.lower()

    def test_demo_login_still_works_while_passwords_are_locked(self, client):
        """A locked password path must not strand someone giving the demo."""
        for _ in range(6):
            self.wrong(client)
        assert client.post("/api/session/demo", json={"role": "owner"}).status_code == 200


class TestAddressAttribution:
    def test_forwarded_header_ignored_unless_a_proxy_is_declared(self, client, monkeypatch):
        """Otherwise a caller invents a new address per request and never locks."""
        import config
        monkeypatch.setattr(config, "TRUST_PROXY", False)
        for i in range(25):
            client.post("/api/session/staff",
                        headers={"X-Forwarded-For": f"10.0.0.{i}"},
                        json={"username": f"u{i}", "password": "wrong"})
        res = client.post("/api/session/staff",
                          headers={"X-Forwarded-For": "10.0.0.250"},
                          json={"username": "another", "password": "wrong"})
        assert res.status_code == 429

    def test_forwarded_header_honoured_when_declared(self, client, monkeypatch):
        import config
        monkeypatch.setattr(config, "TRUST_PROXY", True)
        for _ in range(5):
            client.post("/api/session/staff",
                        headers={"X-Forwarded-For": "203.0.113.9"},
                        json={"username": "owner", "password": "wrong"})
        # A different declared address is a different bucket.
        res = client.post("/api/session/staff",
                          headers={"X-Forwarded-For": "203.0.113.10"},
                          json={"username": "manager", "password": TEST_PASSWORDS["manager"]})
        assert res.status_code == 200
