# TrazeIQ Python SDK (`trazeiq`)

Zero dependencies (stdlib `urllib` only, Python 3.9+). Thin wrapper over `POST {endpoint}/api/v1/events/` — the server owns redaction, fingerprinting, grouping and incident tracking.

## Install

```bash
pip install trazeiq
```

## Usage

```python
import trazeiq

trazeiq.init(
    api_key="YOUR_API_KEY",  # raw key shown once at project creation
    # endpoint="https://api.trazeiq.io",  # optional, this is the default
    environment="production",
    service="payment-api",
)

try:
    process_payment(order)
except Exception:
    trazeiq.capture_exception()  # uses the active exception; never raises
    raise  # TrazeIQ observes, it doesn't swallow

# Plain message with severity + metadata
trazeiq.capture_message(
    "Cache hit ratio dropped below 80%",
    level="warning",
    metadata={"ratio": 0.74},
)
```

With Flask/Django/FastAPI, call `trazeiq.capture_exception()` in your error handler (or decorate a function with `@trazeiq.wrap()`); pass `endpoint=request.path` / `request_method=request.method` / `user_id=...` as needed.

## API

| Symbol | Purpose |
|---|---|
| `init(api_key, endpoint?, environment?, service?, default_metadata?, timeout_seconds?=2.0, enabled?=True)` | Configure. Raises only when `api_key` is missing. |
| `capture_message(message, **opts)` | Send a string event. Empty messages are no-ops. |
| `capture_exception(exc=None, **opts)` | Send the active (or given) exception with formatted traceback. No-op outside a handler when omitted. |
| `wrap(**opts)` | Decorator: reports exceptions, then re-raises. |
| `set_user(id \| None)` | Stamp `user_id` on subsequent events. |
| `add_breadcrumb(crumb)` / `clear_breadcrumbs()` | Buffer context (max 50, sent as `breadcrumbs`). |
| `flush()` | No-op (sends are immediate), kept for API compatibility. |
| `close()` | Disable the client; captures become no-ops. |

Per-event `opts`: `level` (`fatal|error|warning|info|debug`, default `error`), `environment`, `service`, `endpoint`, `request_method`, `user_id`, `ip_address`, `metadata` (dict), `breadcrumbs` (list), `stacktrace`.

## Guarantees

- **Never raises**: transport/DNS/timeout failures are swallowed.
- **Never blocks long**: single POST with a short timeout (default 2s, tunable via `timeout_seconds`), no retries.
- **Backend contract**: sends `X-API-Key` + the `EventInputSerializer` JSON shape to `/api/v1/events/`. Oversized payloads may get HTTP 413; rate limits HTTP 429 — both swallowed client-side by design.
# TrazeIQ-Python-sdk
