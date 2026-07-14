from __future__ import annotations

from collections.abc import Collection
from urllib.parse import urlsplit


def require_https_url(url: str, *, allowed_hosts: Collection[str]) -> str:
    """Reject non-HTTPS and unexpected outbound destinations before network I/O."""

    parsed = urlsplit(str(url or ""))
    hosts = {host.lower() for host in allowed_hosts}
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in hosts:
        raise ValueError("Outbound URL must use HTTPS and an approved host")
    if parsed.username or parsed.password:
        raise ValueError("Outbound URL must not contain user information")
    return url
