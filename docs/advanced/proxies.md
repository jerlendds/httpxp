HTTPXP supports setting up [HTTP proxies](https://en.wikipedia.org/wiki/Proxy_server#Web_proxy_servers) via the `proxy` parameter to be passed on client initialization or top-level API functions like `httpxp.get(..., proxy=...)`.

<div align="center">
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/2/27/Open_proxy_h2g2bob.svg/480px-Open_proxy_h2g2bob.svg.png"/>
    <figcaption><em>Diagram of how a proxy works (source: Wikipedia). The left hand side "Internet" blob may be your HTTPXP client requesting <code>example.com</code> through a proxy.</em></figcaption>
</div>

## HTTP Proxies

To route all traffic (HTTP and HTTPS) to a proxy located at `http://localhost:8030`, pass the proxy URL to the client...

```python
with httpxp.Client(proxy="http://localhost:8030") as client:
    ...
```

For more advanced use cases, pass a mounts `dict`. For example, to route HTTP and HTTPS requests to 2 different proxies, respectively located at `http://localhost:8030`, and `http://localhost:8031`, pass a `dict` of proxy URLs:

```python
proxy_mounts = {
    "http://": httpxp.HTTPTransport(proxy="http://localhost:8030"),
    "https://": httpxp.HTTPTransport(proxy="http://localhost:8031"),
}

with httpxp.Client(mounts=proxy_mounts) as client:
    ...
```

For detailed information about proxy routing, see the [Routing](#routing) section.

!!! tip "Gotcha"
    In most cases, the proxy URL for the `https://` key _should_ use the `http://` scheme (that's not a typo!).

    This is because HTTP proxying requires initiating a connection with the proxy server. While it's possible that your proxy supports doing it via HTTPS, most proxies only support doing it via HTTP.

    For more information, see [FORWARD vs TUNNEL](#forward-vs-tunnel).

## Authentication

Proxy credentials can be passed as the `userinfo` section of the proxy URL. For example:

```python
with httpxp.Client(proxy="http://username:password@localhost:8030") as client:
    ...
```

## Proxy mechanisms

!!! note
    This section describes **advanced** proxy concepts and functionality.

### FORWARD vs TUNNEL

In general, the flow for making an HTTP request through a proxy is as follows:

1. The client connects to the proxy (initial connection request).
2. The proxy transfers data to the server on your behalf.

How exactly step 2/ is performed depends on which of two proxying mechanisms is used:

* **Forwarding**: the proxy makes the request for you, and sends back the response it obtained from the server.
* **Tunnelling**: the proxy establishes a TCP connection to the server on your behalf, and the client reuses this connection to send the request and receive the response. This is known as an [HTTP Tunnel](https://en.wikipedia.org/wiki/HTTP_tunnel). This mechanism is how you can access websites that use HTTPS from an HTTP proxy (the client "upgrades" the connection to HTTPS by performing the TLS handshake with the server over the TCP connection provided by the proxy).

### Troubleshooting proxies

If you encounter issues when setting up proxies, please refer to our [Troubleshooting guide](../troubleshooting.md#proxies).

## SOCKS

In addition to HTTP proxies, the native transport also supports proxies using the SOCKS protocol.
SOCKS support is included in the native transport; no Python SOCKS extra is required.

```python
httpxp.Client(proxy='socks5://user:pass@host:port')
```

See [privacy configuration](wreq.md#proxies-and-local-addresses) for request-level
proxies, exclusions, custom proxy headers, scheme rules, and Unix sockets.
