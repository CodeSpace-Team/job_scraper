"""
Unit tests for retry decorator (src/utils/retry.py).

Tests:
- Successful first attempt
- Success after retries
- Exhaustion of retries raises exception
- Immediate raise of specific exceptions
"""
import pytest
from src.utils.retry import retry


class RetryTestError(Exception):
    """Custom exception for testing retries."""
    pass


def test_retry_success_first():
    """Function should succeed on first attempt."""
    call_count = 0

    @retry(exceptions=(RetryTestError,), tries=3)
    def successful():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = successful()
    assert result == "ok"
    assert call_count == 1


def test_retry_after_failure():
    """Function succeeds after two failures."""
    call_count = 0

    @retry(exceptions=(RetryTestError,), tries=3, delay=0.01)
    def eventually_succeeds():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RetryTestError("retry me")
        return "ok"

    result = eventually_succeeds()
    assert result == "ok"
    assert call_count == 3


def test_retry_exhausted():
    """All retries fail, exception is raised."""
    call_count = 0

    @retry(exceptions=(RetryTestError,), tries=3, delay=0.01)
    def always_fails():
        nonlocal call_count
        call_count += 1
        raise RetryTestError("fail")

    with pytest.raises(RetryTestError):
        always_fails()
    assert call_count == 3


def test_retry_exceptions_to_raise():
    """Certain exceptions are raised immediately without retry."""
    @retry(exceptions=(Exception,), exceptions_to_raise=(ValueError,))
    def raises_value_error():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        raises_value_error()