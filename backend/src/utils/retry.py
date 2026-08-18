"""
retry.py — Retry decorator for robust scraping
================================================

Provides a `@retry` decorator to automatically retry failed operations
with exponential backoff. Useful for network calls, API requests, and
any operation that might experience transient failures.

Usage:
    from src.utils import retry

    @retry(exceptions=(requests.RequestException,), tries=3, delay=1)
    def fetch_data():
        ...

    # If you want to raise certain exceptions immediately:
    @retry(exceptions=(Exception,), exceptions_to_raise=(ValueError,))
    def process():
        ...

    # If whether to retry depends on the exception itself, not just its type:
    @retry(exceptions=(APIError,), should_retry=lambda e: e.code >= 500)
    def call_api():
        ...
"""

import time
from functools import wraps
from typing import Type, Tuple, Optional, Callable, Any


def retry(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    tries: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    exceptions_to_raise: Optional[Tuple[Type[Exception], ...]] = None,
    should_retry: Optional[Callable[..., bool]] = None
) -> Callable:
    """
    Retry decorator with exponential backoff.

    Args:
        exceptions (tuple): Exception classes to catch and retry on.
        tries (int): Maximum number of attempts (including the first).
        delay (float): Initial delay between retries in seconds.
        backoff (float): Multiplier applied to delay after each retry.
        exceptions_to_raise (tuple, optional): If provided, these exceptions
            are NOT caught and will be raised immediately.
        should_retry (callable, optional): Given the caught exception, returns
            True to retry it and False to raise it straight away. Use this when
            the exception's type is not enough to tell a transient failure from
            a permanent one -- an API that reports both "try again in a moment"
            and "you are not allowed to do that" as the same exception class,
            for instance. Left unset, every caught exception is retried, which
            is how this decorator behaved before the option existed.

            Typed as Callable[..., bool] on purpose. Whatever this receives is
            always one of `exceptions`, so a caller passing exceptions=(APIError,)
            is entitled to write a predicate that takes an APIError -- but that
            connection between the two arguments cannot be expressed here, and
            naming a broad type instead would make every such predicate look
            wrong to a type checker.

    Returns:
        Callable: Decorated function.

    Raises:
        The last exception raised if all retries are exhausted.

    Example:
        @retry(exceptions=(ConnectionError, TimeoutError), tries=3, delay=1, backoff=2)
        def fetch_data():
            # ... code that might fail transiently ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            _tries = tries
            _delay = delay

            while _tries > 0:
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    # If this exception type should be raised immediately, do so.
                    if exceptions_to_raise and isinstance(e, exceptions_to_raise):
                        raise

                    # Same idea, but decided per exception rather than per type:
                    # a caller can look inside the exception and say this one is
                    # not worth trying again.
                    if should_retry is not None and not should_retry(e):
                        raise

                    _tries -= 1
                    if _tries == 0:
                        raise  # re-raise the last exception

                    # Wait before retrying
                    time.sleep(_delay)
                    _delay *= backoff  # exponential backoff

            # Should never reach here, but just in case:
            return None

        return wrapper
    return decorator