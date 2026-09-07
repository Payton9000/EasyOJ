"""Request-target helpers shared by views."""

from urllib.parse import urlparse

from flask import request


def safe_referrer(fallback):
    """Return the Referer only when it points at a path on this host.

    Redirecting to a raw header lets an attacker choose where an authenticated
    action lands, so anything cross-host or protocol-relative falls back.
    """
    referrer = request.referrer or ''
    parsed = urlparse(referrer)
    same_host = not parsed.netloc or parsed.netloc.casefold() == request.host.casefold()
    safe_path = parsed.path.startswith('/') and not parsed.path.startswith('//')
    if same_host and safe_path:
        target = parsed.path
        if parsed.query:
            target += '?' + parsed.query
        return target
    return fallback
