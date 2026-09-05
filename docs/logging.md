# Logging

HTTPXP logs completed request headers through the standard Python `httpxp`
logger at INFO level:

```python
import logging
import httpxp

logging.basicConfig(level=logging.INFO)
httpxp.get("https://example.com")
```

A typical record looks like:

```text
INFO:httpxp:HTTP Request: GET https://example.com "HTTP/1.1 200 OK"
```

The native transport does not emit the old Python transport's connection/TLS
trace events. `privacy_options={"connection_verbose": True}` enables native
connection verbosity, but a native Rust logging subscriber is not currently
bridged to Python logging. It does not enable Python wire logs on its own.

For application-level instrumentation, register request and response
[event hooks](advanced/event-hooks.md). Async clients require async hooks.
The CLI's `--verbose` output uses these hooks to display request/response
headers. It does not report individual connection or TLS lifecycle events.

For TLS traffic inspection, [TLS key logging](advanced/wreq.md#tls-key-logging-and-session-caching)
is available separately from application logs.
