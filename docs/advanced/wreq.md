# Privacy configuration

`httpxp` uses a Rust extension backed by wreq. Pass native client configuration
through `privacy_options` on `Client`, `AsyncClient`, `HTTPTransport`,
`AsyncHTTPTransport`, or the module request helpers. Request-specific settings
use `extensions={"private": {...}}` on the existing request methods. Unknown native
option names raise `ValueError`.

Native client options override settings derived from the Python constructor.
For example, `privacy_options={"tls_cert_store_pem": pem_bytes}` replaces the trust
store derived from `verify`. Time durations are expressed in seconds.

The [option reference](privacy-options.md) lists every currently accepted setting,
including TLS, HTTP/1, HTTP/2, and emulation profiles. The binding is under
development; the [coverage audit](wreq-coverage.md) records missing upstream
capabilities and compatibility limitations.

## Proxies and local addresses

The ordinary `proxy=httpxp.Proxy(...)` API supports URL credentials and custom
proxy headers. A native proxy configuration may instead be supplied at client
or request scope:

```python
import httpxp

with httpxp.Client(
    trust_env=False,
    privacy_options={
        "proxy": {
            "url": "http://127.0.0.1:8080",
            "scheme": "all",
            "basic_auth": ("username", "password"),
            "custom_http_headers": [("X-Proxy-Token", "token")],
            "no_proxy": "localhost,127.0.0.1",
        },
    },
) as client:
    response = client.get("https://example.com")
```

A proxy can be a URL string or a mapping with these fields:

| Field | Value |
| --- | --- |
| `url` | Required proxy URL, or socket path for `scheme="unix"` |
| `scheme` | Destination scheme selection: `"all"` (default), `"http"`, `"https"`, or `"unix"` on Unix |
| `basic_auth` | `(username, password)` string pair |
| `custom_http_auth` | Custom Proxy-Authorization value as string or bytes |
| `custom_http_headers` | Sequence of header name/value pairs, as strings or bytes |
| `no_proxy` | Comma-separated wreq exclusion list, or `None` |

URL schemes include HTTP, HTTPS, SOCKS5, and SOCKS5H. `scheme` selects which
**destination** URLs use the proxy; the scheme in `url` selects the connection
protocol to the proxy. Unix socket proxies ignore custom HTTP proxy headers,
matching wreq behavior.

Client option `proxies` accepts an ordered sequence of proxy configurations.
wreq selects the first matching rule; this does not rotate proxies. Client
option `no_proxy=True` clears native proxy rules when applied. Native options
are applied in mapping order, so place `no_proxy` before any rules you want to
retain. Python environment proxy mounts are controlled separately by
`trust_env`; use `trust_env=False` for explicit native routing.

Override a proxy for one request with:

```python
response = client.get(
    "https://example.com",
    extensions={"private": {"proxy": "socks5h://127.0.0.1:9050"}},
)
```

Both client and request options accept `local_address` (one IP address or
`None`), `local_addresses` (an IPv4/IPv6 pair with nullable entries), and
`interface` (an interface name on supported platforms). `uds` is a shorthand
for a Unix socket proxy.

## TLS key logging and session caching

`tls_keylog` accepts an output path or `"env"` to use wreq's `SSLKEYLOGFILE`
lookup. These files contain TLS session secrets; use them for deliberate
traffic inspection. `tls_session_cache` sets the native LRU cache's per-host
session capacity. Enable session reuse with `tls_options.pre_shared_key`:

```python
with httpxp.Client(privacy_options={
    "tls_keylog": "/tmp/httpxp-tls.log",
    "tls_session_cache": 8,
    "tls_options": {"pre_shared_key": True, "session_ticket": True},
}) as client:
    response = client.get("https://example.com")
```

## WebSockets

`Client.websocket` accepts `ws`, `wss`, `http`, and `https` URLs. The async
counterpart is awaited before entering its async context manager:

```python
with httpxp.Client() as client:
    with client.websocket("ws://localhost:3000/ws", protocols=["chat"]) as socket:
        socket.send_text("hello")
        message = socket.receive()
        print(message.data if message else "closed")

async def echo():
    async with httpxp.AsyncClient() as client:
        async with await client.websocket("ws://localhost:3000/ws") as socket:
            await socket.send_json({"hello": "world"})
            message = await socket.receive()
            return message
```

For extended CONNECT over HTTP/2, enable HTTP/2 on the client and pass
`version="2"` to `websocket`. The peer must advertise support for extended
CONNECT. `examples/private_websocket.py` demonstrates HTTP/1, HTTP/2, and concurrent
async sending and receiving.

WebSocket builder keyword options are `version`, `protocols`, `accept_key`,
`max_frame_size`, `read_buffer_size`, `write_buffer_size`,
`max_write_buffer_size`, `max_message_size`, and `accept_unmasked_frames`.
Buffer and message sizes are in bytes. The native defaults apply when omitted.

Messages expose `type`, `data`, and `code` fields. Text, binary, ping, pong, and
close messages can be received. Use `send_text`, `send_bytes`, `send_json`,
`ping`, or `send(WebSocketMessage(...))` to send messages. Iteration stops at a
close message or end of stream. `response` contains handshake status, headers,
and HTTP version; `protocol` contains the negotiated subprotocol.

Close sockets explicitly or use their context managers to release connection
capacity. Handshake authentication currently applies the initial auth request;
challenge-based authentication and redirect handling remain incomplete.

## Custom DNS and connection groups

A client-level `dns_resolver` callback receives the hostname and returns an
iterable of `(IP_address_string, port)` pairs:

```python
with httpxp.Client(trust_env=False, privacy_options={
    "dns_resolver": lambda host: [("127.0.0.1", 8080)],
}) as client:
    response = client.get("http://internal.example")
```

The callback is synchronous, including with `AsyncClient`. It runs on a Rust
blocking worker; it must be thread-safe when requests run concurrently. Its
exceptions propagate to the caller. A nonzero returned port is used when the
URL has no explicit port. Port zero selects the URL scheme's default; an
explicit URL port overrides the callback's port. Static `resolve` entries take
precedence over the callback. Numeric IP destinations bypass DNS.

Connect timeout and async cancellation stop waiting for the resolver and free
request capacity. They cannot interrupt Python code already executing inside
the callback; that code continues until it returns. Coroutine callbacks are
not supported.

To partition native pooled connections by a logical identity, use a request
`group` with a string or unsigned 64-bit integer:

```python
response = client.get(
    "https://example.com",
    extensions={"private": {"group": "account-one"}},
)
```

Requests in the same group can reuse connections. Different groups use separate
pool entries. The string `"1"` and integer `1` are distinct. Grouping does not
partition the Python client's cookie jar or authentication configuration.

See [the API coverage audit](wreq-coverage.md) for implemented mappings and
remaining gaps.
