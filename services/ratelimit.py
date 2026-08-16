"""Sliding-window rate limiting for authentication attempts.

Two dimensions, because they stop different attacks:

  * per username -- someone guessing at one account
  * per client address -- someone spraying one password across many accounts,
    which never trips a per-username counter

Both are counted for *attempted* usernames whether or not the account exists.
Limiting only real accounts would turn the lockout itself into an oracle: an
attacker could learn which usernames are valid purely from which ones can be
locked.

Failures expire on a sliding window rather than a fixed one, and a successful
sign-in clears that username's counter, so an ordinary person who mistypes a
few times is not punished for the rest of the hour.

State is in memory, like sessions. That means a restart forgives everyone and
several worker processes would each keep their own tally -- acceptable for a
single-process showcase, and called out in the README as something a real
deployment must replace with a shared store.
"""
import threading
import time


class RateLimiter:
    def __init__(self, max_attempts, window_seconds, lockout_seconds, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.lockout = lockout_seconds
        self._clock = clock
        self._failures = {}      # key -> [timestamps]
        self._locked_until = {}  # key -> timestamp
        self._lock = threading.Lock()

    def _prune(self, key, now):
        stamps = [t for t in self._failures.get(key, []) if now - t < self.window]
        if stamps:
            self._failures[key] = stamps
        else:
            self._failures.pop(key, None)
        return stamps

    def retry_after(self, key):
        """Seconds until this key may try again; 0 when it is free to proceed."""
        if not key:
            return 0
        now = self._clock()
        with self._lock:
            until = self._locked_until.get(key)
            if until is None:
                return 0
            if now >= until:
                # Lockout served: forget it and the failures that caused it, so
                # the caller starts from a clean slate rather than re-locking
                # on their next single mistake.
                self._locked_until.pop(key, None)
                self._failures.pop(key, None)
                return 0
            return max(1, int(round(until - now)))

    def is_limited(self, key):
        return self.retry_after(key) > 0

    def record_failure(self, key):
        """Count a failed attempt. Returns seconds of lockout, or 0."""
        if not key:
            return 0
        now = self._clock()
        with self._lock:
            stamps = self._prune(key, now)
            stamps.append(now)
            self._failures[key] = stamps
            if len(stamps) >= self.max_attempts:
                self._locked_until[key] = now + self.lockout
                return self.lockout
        return 0

    def record_success(self, key):
        if not key:
            return
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def failure_count(self, key):
        with self._lock:
            return len(self._prune(key, self._clock()))

    def reset(self):
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


# Per-account: tight, because a real person rarely misses five times.
BY_USERNAME = RateLimiter(max_attempts=5, window_seconds=900, lockout_seconds=900)

# Per-address: looser, since a shop counter may legitimately share one IP
# between several staff, but low enough to stop spraying.
BY_ADDRESS = RateLimiter(max_attempts=20, window_seconds=900, lockout_seconds=900)


def check(username, address):
    """Seconds to wait before another attempt is allowed, or 0.

    The larger of the two windows wins, so clearing one does not let a caller
    slip past the other.
    """
    return max(
        BY_USERNAME.retry_after((username or "").strip().lower()),
        BY_ADDRESS.retry_after(address),
    )


def record_failure(username, address):
    BY_USERNAME.record_failure((username or "").strip().lower())
    BY_ADDRESS.record_failure(address)


def record_success(username, address):
    """Clear the username on success.

    The address counter is deliberately left alone: one correct password among
    many wrong ones is exactly what a successful spray looks like, so a single
    success should not wipe the evidence of the attempts around it.
    """
    BY_USERNAME.record_success((username or "").strip().lower())


def reset_all():
    BY_USERNAME.reset()
    BY_ADDRESS.reset()
