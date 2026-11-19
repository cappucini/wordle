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
