"""A shared, resilient HTTP session.

Centralises outbound HTTP so every request gets:

* **automatic retries with exponential backoff** on transient failures
  (connection errors and 429/5xx responses);
* a **connection pool** reused across fetches (faster, fewer sockets);
* a consistent ``User-Agent``.

Both the event parser and the desktop image loader use this session, so network
resilience is defined in exactly one place.
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "PokeTrack/1.1 (+https://github.com/poketrack)"
DEFAULT_TIMEOUT = 15  # seconds


def build_session(
    total_retries: int = 3,
    backoff_factor: float = 0.6,
    pool_size: int = 10,
) -> requests.Session:
    """Create a :class:`requests.Session` with a retrying HTTP adapter."""
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        backoff_factor=backoff_factor,         # 0.6 -> 0.6s, 1.2s, 2.4s …
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_size, pool_maxsize=pool_size)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


# Module-level singleton — safe to share across threads.
SESSION: requests.Session = build_session()
