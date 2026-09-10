"""TrazeIQ Python SDK — thin wrapper over ``POST {endpoint}/api/v1/events/``.

Zero dependencies (stdlib ``urllib`` only). Mirrors the backend
``EventInputSerializer`` fields; the server owns secret redaction,
fingerprinting, grouping and incident tracking.

Guarantees (the System Agent contract from the TrazeIQ spec):
- never raises: ``capture_message`` / ``capture_exception`` swallow all
  transport errors and return ``None``;
- never blocks long: short timeout (default 2s), no retries.

Typical usage::

    import trazeiq

    trazeiq.init(
        api_key="YOUR_API_KEY",
        environment="production",
        service="payment-api",
    )

    try:
        process_payment(order)
    except Exception:
        trazeiq.capture_exception()  # uses the active exception
        raise  # TrazeIQ observes, it doesn't swallow
"""

from __future__ import annotations

import functools
import json
import sys
import traceback
import urllib.request
from typing import Any, Callable, Dict, List, Optional

DEFAULT_ENDPOINT = "https://api.trazeiq.io"
DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_BREADCRUMBS = 50

_LEVELS = ("fatal", "error", "warning", "info", "debug")

_config: Optional[Dict[str, Any]] = None
_user_id: Optional[str] = None
_breadcrumbs: List[Dict[str, Any]] = []


def init(
    api_key: str,
    endpoint: str = DEFAULT_ENDPOINT,
    environment: str = "",
    service: str = "",
    default_metadata: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    enabled: bool = True,
) -> None:
    """Configure the SDK. Must be called before any capture call."""
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("trazeiq: init() requires a non-empty api_key.")
    global _config
    _config = {
        "api_key": api_key,
        "events_url": endpoint.rstrip("/") + "/api/v1/events/",
        "environment": environment,
        "service": service,
        "default_metadata": dict(default_metadata or {}),
        "timeout_seconds": timeout_seconds,
        "enabled": enabled,
    }


def _reset_for_tests() -> None:
    """Reset internal state (tests only)."""
    global _config, _user_id, _breadcrumbs
    _config = None
    _user_id = None
    _breadcrumbs = []


def set_user(user_id: Optional[str]) -> None:
    """Stamp ``user_id`` on subsequent events."""
    global _user_id
    _user_id = user_id


def add_breadcrumb(crumb: Dict[str, Any]) -> None:
    """Buffer context for subsequent events (kept max 50)."""
    global _breadcrumbs
    _breadcrumbs = [*_breadcrumbs, dict(crumb)][-MAX_BREADCRUMBS:]


def clear_breadcrumbs() -> None:
    """Clear buffered breadcrumbs."""
    global _breadcrumbs
    _breadcrumbs = []


def close() -> None:
    """Disable the client — subsequent captures are no-ops."""
    if _config is not None:
        _config["enabled"] = False


def _build_payload(message: str, **opts: Any) -> Dict[str, Any]:
    cfg = _config or {}
    metadata = dict(cfg.get("default_metadata", {}))
    metadata.update(opts.get("metadata") or {})
    return {
        "message": message,
        "stacktrace": opts.get("stacktrace", ""),
        "level": opts.get("level", "error"),
        "environment": opts.get("environment", cfg.get("environment", "")),
        "service": opts.get("service", cfg.get("service", "")),
        "endpoint": opts.get("endpoint", ""),
        "request_method": opts.get("request_method", ""),
        "user_id": opts.get("user_id", _user_id or ""),
        "ip_address": opts.get("ip_address", ""),
        "metadata": metadata,
        "breadcrumbs": (
            opts.get("breadcrumbs")
            if opts.get("breadcrumbs") is not None
            else list(_breadcrumbs)
        ),
    }


def _send(payload: Dict[str, Any]) -> None:
    """POST one event. Never raises — all transport errors are swallowed."""
    cfg = _config
    if not cfg or not cfg["enabled"]:
        return
    try:
        req = urllib.request.Request(
            cfg["events_url"],
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": cfg["api_key"],
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=cfg["timeout_seconds"]):
            pass
    except Exception:
        # Monitoring must never break the host app.
        return


def capture_message(message: str, **opts: Any) -> None:
    """Report a string message. Never raises; empty messages are no-ops."""
    if not isinstance(message, str) or not message:
        return
    _send(_build_payload(message, **opts))


def capture_exception(exc: Optional[BaseException] = None, **opts: Any) -> None:
    """Report the active (or given) exception. Never raises.

    When ``exc`` is omitted, the current ``sys.exc_info()`` is used, so the
    idiomatic call inside ``except:`` takes no arguments. Outside an
    exception handler with no ``exc`` given, this is a no-op.
    """
    if exc is None:
        exc = sys.exc_info()[1]
    if exc is None:
        return
    if "stacktrace" not in opts:
        try:
            opts["stacktrace"] = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        except Exception:
            opts["stacktrace"] = ""
    message = str(exc) or type(exc).__name__
    _send(_build_payload(message, **opts))


def wrap(**capture_opts: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: report exceptions, then re-raise (never swallows)."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                capture_exception(exc, **capture_opts)
                raise

        return inner

    return decorator


def flush() -> None:
    """No-op (sends are immediate), kept for API compatibility."""


__all__ = [
    "init",
    "capture_message",
    "capture_exception",
    "wrap",
    "set_user",
    "add_breadcrumb",
    "clear_breadcrumbs",
    "flush",
    "close",
]
