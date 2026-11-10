"""Máquina de estados del lockout progresivo (task 1.8/1.9, design D6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.auth.lockout import (
    LockoutState,
    is_locked,
    normalize,
    register_failure,
    register_success,
    retry_after_seconds,
)

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
MAX_LOCK_MINUTES = 24 * 60


def _fail_n(state: LockoutState, times: int, now: datetime = NOW) -> LockoutState:
    for _ in range(times):
        state = register_failure(state, now)
    return state


def test_four_failures_do_not_lock() -> None:
    state = _fail_n(LockoutState(), 4)

    assert state.failed_login_count == 4
    assert is_locked(state, NOW) is False


def test_fifth_failure_locks_for_fifteen_minutes() -> None:
    state = _fail_n(LockoutState(), 5)

    assert is_locked(state, NOW) is True
    assert state.locked_until == NOW + timedelta(minutes=15)
    assert retry_after_seconds(state, NOW) == 900
    assert state.lockout_strikes == 1


def test_locked_account_ignores_a_correct_password() -> None:
    locked = _fail_n(LockoutState(), 5)

    state = register_success(locked, NOW)

    assert is_locked(state, NOW) is True
    assert state.locked_until == locked.locked_until


def test_expired_window_returns_to_normal_with_zeroed_counter() -> None:
    locked = _fail_n(LockoutState(), 5)
    later = NOW + timedelta(minutes=16)

    state = normalize(locked, later)

    assert is_locked(state, later) is False
    assert state.failed_login_count == 0
    assert state.locked_until is None
    assert state.lockout_strikes == 1


def test_second_consecutive_lockout_lasts_thirty_minutes() -> None:
    first = _fail_n(LockoutState(), 5)
    after_expiry = normalize(first, NOW + timedelta(minutes=16))

    second = _fail_n(after_expiry, 5, NOW + timedelta(minutes=16))

    assert second.lockout_strikes == 2
    assert second.locked_until == NOW + timedelta(minutes=16 + 30)
    assert retry_after_seconds(second, NOW + timedelta(minutes=16)) == 1800


def test_lockout_window_is_capped_at_twenty_four_hours() -> None:
    state = LockoutState(failed_login_count=4, lockout_strikes=20)

    locked = register_failure(state, NOW)

    assert locked.locked_until == NOW + timedelta(minutes=MAX_LOCK_MINUTES)
    assert retry_after_seconds(locked, NOW) == MAX_LOCK_MINUTES * 60


def test_successful_login_resets_counters_and_strikes() -> None:
    state = LockoutState(
        failed_login_count=3,
        lockout_strikes=2,
        locked_until=NOW - timedelta(minutes=1),
    )

    reset = register_success(state, NOW)

    assert reset.failed_login_count == 0
    assert reset.lockout_strikes == 0
    assert reset.locked_until is None


def test_retry_after_is_zero_when_not_locked() -> None:
    assert retry_after_seconds(LockoutState(failed_login_count=2), NOW) == 0
