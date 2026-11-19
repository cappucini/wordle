"""app/rate_limit.py: counting attempts inside a time window."""

from app.rate_limit import AttemptLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_limiter(max_attempts=3, window_seconds=60):
    clock = FakeClock()
    return AttemptLimiter(max_attempts, window_seconds, clock=clock), clock


def test_nothing_is_blocked_to_begin_with():
    limiter, _ = make_limiter()

    assert limiter.seconds_until_allowed("erica") == 0


def test_blocked_once_the_limit_is_reached():
    limiter, _ = make_limiter(max_attempts=3)

    limiter.record("erica")
    limiter.record("erica")
    assert limiter.seconds_until_allowed("erica") == 0
    limiter.record("erica")

    assert limiter.seconds_until_allowed("erica") > 0


def test_each_key_is_counted_separately():
    limiter, _ = make_limiter(max_attempts=1)

    limiter.record("erica")

    assert limiter.seconds_until_allowed("erica") > 0
    assert limiter.seconds_until_allowed("sam") == 0


def test_says_how_long_until_the_oldest_attempt_leaves_the_window():
    limiter, clock = make_limiter(max_attempts=2, window_seconds=60)
    limiter.record("erica")
    clock.advance(20)
    limiter.record("erica")
    clock.advance(10)

    # the first attempt was 30 seconds ago, so it counts for 30 more
    assert limiter.seconds_until_allowed("erica") == 30


def test_allowed_again_once_the_window_has_passed():
    limiter, clock = make_limiter(max_attempts=2, window_seconds=60)
    limiter.record("erica")
    limiter.record("erica")

    clock.advance(59)
    assert limiter.seconds_until_allowed("erica") > 0
    clock.advance(1)

    assert limiter.seconds_until_allowed("erica") == 0


def test_old_attempts_drop_out_one_at_a_time():
    limiter, clock = make_limiter(max_attempts=2, window_seconds=60)
    limiter.record("erica")
    clock.advance(40)
    limiter.record("erica")
    clock.advance(20)  # the first attempt has now left the window

    assert limiter.seconds_until_allowed("erica") == 0
    limiter.record("erica")
    assert limiter.seconds_until_allowed("erica") > 0


def test_clear_forgets_one_key():
    limiter, _ = make_limiter(max_attempts=1)
    limiter.record("erica")
    limiter.record("sam")

    limiter.clear("erica")

    assert limiter.seconds_until_allowed("erica") == 0
    assert limiter.seconds_until_allowed("sam") > 0


def test_reset_forgets_everything():
    limiter, _ = make_limiter(max_attempts=1)
    limiter.record("erica")
    limiter.record("sam")

    limiter.reset()

    assert limiter.seconds_until_allowed("erica") == 0
    assert limiter.seconds_until_allowed("sam") == 0


def test_keys_whose_attempts_have_all_expired_are_forgotten():
    # otherwise trying a million made-up usernames would fill the server's memory for good
    limiter, clock = make_limiter(max_attempts=3, window_seconds=60)
    for number in range(500):
        limiter.record(f"made_up_{number}")
    assert limiter.tracked_keys() == 500

    clock.advance(61)
    limiter.record("erica")  # any activity sweeps out what has expired

    assert limiter.tracked_keys() == 1


# ---------- attempt(): check and count in one step ----------


def test_attempt_counts_itself_when_allowed():
    limiter, _ = make_limiter(max_attempts=2)

    assert limiter.attempt("erica") == 0
    assert limiter.attempt("erica") == 0

    assert limiter.attempt("erica") > 0


def test_a_refused_attempt_is_not_counted():
    # otherwise someone who keeps trying while blocked would never be let back in
    limiter, clock = make_limiter(max_attempts=1, window_seconds=60)
    limiter.attempt("erica")
    for _ in range(50):
        assert limiter.attempt("erica") > 0

    clock.advance(60)

    assert limiter.attempt("erica") == 0


def test_attempts_made_at_the_same_instant_cannot_exceed_the_limit():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    limiter, _ = make_limiter(max_attempts=10)
    start = threading.Barrier(40)

    def attempt(_):
        start.wait(timeout=10)
        return limiter.attempt("erica")

    with ThreadPoolExecutor(40) as pool:
        results = list(pool.map(attempt, range(40)))

    assert results.count(0) == 10


def test_forgive_takes_back_the_latest_attempt():
    limiter, _ = make_limiter(max_attempts=2)
    limiter.attempt("erica")
    limiter.attempt("erica")
    assert limiter.attempt("erica") > 0

    limiter.forgive("erica")

    assert limiter.attempt("erica") == 0


def test_forgive_with_nothing_counted_does_nothing():
    limiter, _ = make_limiter()

    limiter.forgive("erica")

    assert limiter.attempt("erica") == 0


# ---------- limits read from settings ----------


def test_a_limit_uses_its_default_when_no_setting_is_given():
    from app.api.v1.rate_limits import limit_from_environment

    assert limit_from_environment("MAX_SIGNUPS_PER_ADDRESS", 20, environ={}) == 20


def test_a_limit_can_be_set_from_the_environment():
    from app.api.v1.rate_limits import limit_from_environment

    environ = {"MAX_SIGNUPS_PER_ADDRESS": "1000"}

    assert limit_from_environment("MAX_SIGNUPS_PER_ADDRESS", 20, environ=environ) == 1000


def test_a_setting_that_is_not_a_positive_whole_number_stops_the_server_starting():
    import pytest

    from app.api.v1.rate_limits import limit_from_environment

    for bad in ["", "ten", "0", "-5", "2.5"]:
        with pytest.raises(ValueError, match="MAX_SIGNUPS_PER_ADDRESS"):
            limit_from_environment("MAX_SIGNUPS_PER_ADDRESS", 20, environ={"MAX_SIGNUPS_PER_ADDRESS": bad})


def test_the_limits_in_force_are_the_documented_defaults():
    # the test stack sets none of the settings, so these are what production gets too
    from app.api.v1 import rate_limits

    assert rate_limits.failed_logins_by_username.max_attempts == 10
    assert rate_limits.failed_logins_by_address.max_attempts == 30
    assert rate_limits.signups_by_address.max_attempts == 20
    assert rate_limits.refused_signups_by_address.max_attempts == 30
