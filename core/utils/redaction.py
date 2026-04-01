from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit, urlunsplit


_SENSITIVE_QUERY_KEYS = {
    "password",
    "passwd",
    "pass",
    "pwd",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "key",
    "secret",
    "signature",
}


def redact_url(value: str | None) -> str:
    """Redact credentials in URLs for logs/errors.

    - Masks userinfo in authority: scheme://user:pass@host -> scheme://user:***@host
    - Masks sensitive query params: ?password=... -> ?password=***
    """
    if not value:
        return ""

    s = str(value)

    # Fast-path: nothing that looks like credentials.
    if "@" not in s and "password=" not in s and "passwd=" not in s and "token=" not in s and "api_key=" not in s:
        return s

    try:
        parts = urlsplit(s)
    except Exception:
        # Best-effort fallback: mask anything between ':' and '@'
        if "@" in s and "://" in s:
            prefix, rest = s.split("://", 1)
            if "@" in rest:
                userinfo, hostrest = rest.split("@", 1)
                if ":" in userinfo:
                    user = userinfo.split(":", 1)[0]
                    return f"{prefix}://{user}:***@{hostrest}"
        return s

    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostport = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:***@{hostport}"

    query = parts.query
    if query:
        items = []
        for k, v in parse_qsl(query, keep_blank_values=True):
            if k.lower() in _SENSITIVE_QUERY_KEYS:
                items.append((k, "***"))
            else:
                items.append((k, v))
        # Re-encode minimally (avoids importing urlencode to keep dependencies tiny)
        query = "&".join([f"{k}={v}" if v != "" else k for k, v in items])

    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def strip_url_userinfo(value: str | None) -> str:
    """Remove user:pass@ part from URL (safe for storing/returning to clients)."""
    if not value:
        return ""
    s = str(value)
    try:
        parts = urlsplit(s)
    except Exception:
        # Best effort: remove up to '@' after scheme
        if "://" in s and "@" in s:
            prefix, rest = s.split("://", 1)
            return f"{prefix}://{rest.split('@', 1)[1]}"
        return s

    netloc = parts.netloc
    if "@" in netloc:
        _userinfo, hostport = netloc.rsplit("@", 1)
        netloc = hostport
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

