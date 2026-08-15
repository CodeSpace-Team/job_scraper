"""
Unit tests for retry decorator (src/utils/retry.py).

The @retry decorator is a critical resilience component used throughout
the pipeline to handle transient failures in:
- HTTP requests (OfferZen, PNet, Claude API)
- JobSpy scraping (Indeed, LinkedIn)
- External API calls (Google Sheets, Anthropic)

This module verifies that the decorator behaves correctly in all expected
scenarios, including successful first attempts, failures that eventually
succeed, complete exhaustion, and immediate raising of specific exceptions.

Why these tests matter:
- Retry logic prevents pipeline crashes from temporary network glitches.
- It must not delay or hang indefinitely (backoff and retry limits).
- It must propagate errors correctly when all retries are exhausted.
- Certain exceptions (like ValueError) should not be retried.
"""
import pytest
from src.utils.retry import retry


class RetryTestError(Exception):
    """
    Custom exception used exclusively for testing retry behavior.

    This allows us to distinguish between our own test failures and
    unintended exceptions that might be raised by the test environment.
    We use it as the primary exception type that the decorator should retry on.
    """
    pass


def test_retry_success_first():
    """
    Test that the decorator executes the function only once on success.

    Scenario:
    - A function that always succeeds (no exceptions raised).
    - Decorated with @retry specifying 3 attempts.

    Expected behavior:
    - The function is called exactly once (call_count == 1).
    - The return value is preserved ('ok').
    - No retries are attempted.

    Why this matters:
    - Ensures there is no performance penalty for successful operations.
    - Verifies that the decorator does not add unnecessary overhead.
    - Confirms that the first attempt is not counted as a retry.

    Edge cases covered:
    - The function runs immediately.
    - No delay is introduced.
    """
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
    """
    Test that retries occur and the function eventually succeeds.

    Scenario:
    - A function that fails the first two times (raises RetryTestError).
    - Succeeds on the third call.
    - Decorated with @retry with tries=3 and a small delay for speed.

    Expected behavior:
    - The function is called 3 times (call_count == 3).
    - The final return value is 'ok'.
    - The decorator retries after each failure with exponential backoff.

    Why this matters:
    - Verifies that retries are attempted on recoverable errors.
    - Confirms that the function can recover after transient failures.
    - Ensures the decorator does not give up prematurely.

    Edge cases covered:
    - The failure count is less than the total tries.
    - The decorator continues executing despite previous exceptions.
    - The final success is returned correctly.
    """
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
    """
    Test that when all retries are exhausted, the last exception is raised.

    Scenario:
    - A function that always raises RetryTestError.
    - Decorated with @retry with tries=3.

    Expected behavior:
    - The function is called exactly 3 times (call_count == 3).
    - After the last attempt, RetryTestError is propagated to the caller.
    - No further attempts are made.

    Why this matters:
    - Ensures that the pipeline does not enter an infinite loop.
    - The error must reach the caller for proper logging and alerting.
    - Prevents silent failures where the code would keep retrying forever.

    Edge cases covered:
    - All attempts fail.
    - The exception is raised with the correct type.
    - The caller receives the exception to handle appropriately.
    """
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
    """
    Test that certain exceptions are raised immediately without retry.

    Scenario:
    - The decorator is configured to retry on Exception, but to raise
      ValueError immediately (no retry).
    - The decorated function raises ValueError.

    Expected behavior:
    - ValueError is raised immediately (no retries).
    - The exception is not caught by the retry logic.
    - The function is called only once (call_count would be 1, but we don't track it here).

    Why this matters:
    - Not all exceptions are recoverable (e.g., programming errors, invalid input).
    - Retrying on such exceptions would be wasteful and hide bugs.
    - Allows the caller to handle these exceptions appropriately.

    Edge cases covered:
    - The exceptions_to_raise list is respected.
    - The retry loop is bypassed for these exceptions.
    - The exception type remains unchanged.
    """
    @retry(exceptions=(Exception,), exceptions_to_raise=(ValueError,))
    def raises_value_error():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        raises_value_error()