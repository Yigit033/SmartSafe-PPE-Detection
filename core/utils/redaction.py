from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlsplit, urlunsplit


def stream_log_url_detail_enabled() -> bool:
    """When False, logs omit upstream host/path (STREAM_LOG_URL_DETAIL=0)."""
    return os.getenv("STREAM_LOG_URL_DETAIL", "1").strip().lower() in ("1", "true", "yes", "on")


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

    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def format_upstream_url_for_log(
    url: str | None,
    *,
    company_id: str | None = None,
    camera_id: str | None = None,
    label: str = "",
) -> str:
    """Log upstream camera/DVR URLs without leaking host/path when disabled.

    STREAM_LOG_URL_DETAIL=1 (default): redact_url (credentials masked; host/path visible).
    STREAM_LOG_URL_DETAIL=0: identifiers only — use in production log aggregation.
    """
    if not url:
        return ""
    if stream_log_url_detail_enabled():
        return redact_url(str(url))
    suffix = f" camera_id={camera_id}" if camera_id else ""
    suffix += f" company_id={company_id}" if company_id else ""
    extra = f" ({label})" if label else ""
    return f"<upstream redacted{suffix}{extra}>"


def sanitize_camera_record_for_log(record: dict | None) -> dict:
    """Shallow copy of a camera/DVR row safe for logs (passwords never logged raw)."""
    if not record or not isinstance(record, dict):
        return {}
    sensitive_keys = ("password", "passwd", "api_key", "apikey", "secret", "token")
    location_keys = (
        "ip_address",
        "stream_path",
        "rtsp_url",
        "connection_url",
        "gateway_url",
        "username",
    )
    out: dict = {}
    for k, v in record.items():
        if k in sensitive_keys and v:
            out[k] = "***"
        elif not stream_log_url_detail_enabled() and k in location_keys and v:
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


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
