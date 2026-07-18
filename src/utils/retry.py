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
"""

import time
from functools import wraps
from typing import Type, Tuple, Optional, Callable, Any


def retry(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    tries: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    exceptions_to_raise: Optional[Tuple[Type[Exception], ...]] = None
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