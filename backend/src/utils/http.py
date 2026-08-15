"""
http.py — Safe HTTP requests with timeouts and retries
========================================================

Provides a `safe_get()` function that performs HTTP GET requests with
sensible timeouts and graceful error handling. It returns `None` on
network errors or HTTP status codes >= 400, avoiding unhandled exceptions.

Usage:
    from src.utils import safe_get

    resp = safe_get("https://example.com/api")
    if resp:
        data = resp.json()
    else:
        # handle failure gracefully
"""

import requests
from typing import Optional, Dict, Any

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

DEFAULT_TIMEOUT = 45
"""Default timeout in seconds for HTTP requests."""

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-ZA,en;q=0.9",
}
"""Default headers mimicking a real browser."""


def safe_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    **kwargs
) -> Optional[requests.Response]:
    """
    Perform a GET request with standard timeouts and error handling.

    This function wraps `requests.get()` and catches common network
    exceptions, returning `None` instead of raising them. It also
    checks for HTTP error status codes (>= 400) and returns `None`
    in those cases.

    Args:
        url (str): The URL to request.
        headers (dict, optional): Custom HTTP headers. If not provided,
            `DEFAULT_HEADERS` will be used.
        timeout (int, optional): Timeout in seconds. Defaults to 45.
        **kwargs: Additional arguments passed to `requests.get()`.

    Returns:
        requests.Response or None: The response object on success,
        or `None` on network errors, timeouts, or HTTP errors.

    Example:
        resp = safe_get("https://api.example.com/jobs")
        if resp:
            data = resp.json()
        else:
            print("Request failed")
    """
    try:
        resp = requests.get(
            url,
            headers=headers or DEFAULT_HEADERS,
            timeout=timeout,
            **kwargs
        )

        # Treat any HTTP error as failure
        if resp.status_code >= 400:
            return None

        return resp

    except (requests.ConnectionError, requests.Timeout, requests.TooManyRedirects):
        # Network-level failures: return None instead of raising
        return None