# Extensions

Extensions carry transport-specific request settings and response metadata.
Custom transports may support their own keys. The default native transport
supports the keys below.

## Request extensions

### `private`

A mapping of request-specific privacy settings. These override corresponding
native client settings where a request override exists:

```python
import httpxp

with httpxp.Client(privacy_options={"emulation": "Chrome149"}) as client:
    response = client.get(
        "https://example.com",
        extensions={"private": {"version": "2", "group": "account-one"}},
    )
```

Use an HTTP/2-enabled client (`http2=True`) when requesting HTTP/2. See the
[privacy guide](wreq.md) and [complete option reference](privacy-options.md)
for accepted keys, types, and precedence. Client settings use `privacy_options`;
request extensions use `private`.

### `timeout`

A mapping of `connect`, `read`, `write`, and `pool` durations in seconds or
`None`. Prefer the public `timeout=` argument. Read, write, and pool values are
forwarded per request. The native connect timeout currently comes from the
client's timeout or `privacy_options["connect_timeout"]`; per-request connect
overrides are not implemented. The upload write watchdog also counts time
waiting for Python upload producers.

## Response extensions

`http_version` contains bytes such as `b"HTTP/1.1"` or `b"HTTP/2"`.
`response.http_version` exposes the decoded string.

When `privacy_options={"tls_info": True}` is enabled, a TLS response can include
`tls_info={"peer_certificate": der_bytes}`. This is the peer leaf certificate,
not the full certificate chain.

The default transport does not currently expose `trace`, `sni_hostname`, or
`target` request handling, or `network_stream`, `stream_id`, trailers, and
original reason phrases on responses. Unknown top-level extensions can be
carried on a request for custom transports; carrying them does not imply native
support. Unknown keys *inside* `private` raise `ValueError`.

For a custom destination address while retaining certificate hostname checks,
keep the hostname in the URL and use the client's `resolve` or `dns_resolver`
privacy settings. For WebSocket upgrades use the documented
[WebSocket API](wreq.md#websockets). For request/response instrumentation use
[event hooks](event-hooks.md).
