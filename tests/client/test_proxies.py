import pytest

import httpxp


def test_socks_proxy():
    url = httpxp.URL("http://www.example.com")

    for proxy in ("socks5://localhost/", "socks5h://localhost/"):
        client = httpxp.Client(proxy=proxy)
        transport = client._transport_for_url(url)
        assert isinstance(transport, httpxp.HTTPTransport)
        assert transport._options["proxy"] == proxy

        async_client = httpxp.AsyncClient(proxy=proxy)
        async_transport = async_client._transport_for_url(url)
        assert isinstance(async_transport, httpxp.AsyncHTTPTransport)
        assert async_transport._transport._options["proxy"] == proxy


PROXY_URL = "http://[::1]"


@pytest.mark.parametrize(
    ["url", "proxies", "expected"],
    [
        ("http://example.com", {}, None),
        ("http://example.com", {"https://": PROXY_URL}, None),
        ("http://example.com", {"http://example.net": PROXY_URL}, None),
        # Using "*" should match any domain name.
        ("http://example.com", {"http://*": PROXY_URL}, PROXY_URL),
        ("https://example.com", {"http://*": PROXY_URL}, None),
        # Using "example.com" should match example.com, but not www.example.com
        ("http://example.com", {"http://example.com": PROXY_URL}, PROXY_URL),
        ("http://www.example.com", {"http://example.com": PROXY_URL}, None),
        # Using "*.example.com" should match www.example.com, but not example.com
        ("http://example.com", {"http://*.example.com": PROXY_URL}, None),
        ("http://www.example.com", {"http://*.example.com": PROXY_URL}, PROXY_URL),
        # Using "*example.com" should match example.com and www.example.com
        ("http://example.com", {"http://*example.com": PROXY_URL}, PROXY_URL),
        ("http://www.example.com", {"http://*example.com": PROXY_URL}, PROXY_URL),
        ("http://wwwexample.com", {"http://*example.com": PROXY_URL}, None),
        # ...
        ("http://example.com:443", {"http://example.com": PROXY_URL}, PROXY_URL),
        ("http://example.com", {"all://": PROXY_URL}, PROXY_URL),
        ("http://example.com", {"http://": PROXY_URL}, PROXY_URL),
        ("http://example.com", {"all://example.com": PROXY_URL}, PROXY_URL),
        ("http://example.com", {"http://example.com": PROXY_URL}, PROXY_URL),
        ("http://example.com", {"http://example.com:80": PROXY_URL}, PROXY_URL),
        ("http://example.com:8080", {"http://example.com:8080": PROXY_URL}, PROXY_URL),
        ("http://example.com:8080", {"http://example.com": PROXY_URL}, PROXY_URL),
        (
            "http://example.com",
            {
                "all://": PROXY_URL + ":1",
                "http://": PROXY_URL + ":2",
                "all://example.com": PROXY_URL + ":3",
                "http://example.com": PROXY_URL + ":4",
            },
            PROXY_URL + ":4",
        ),
        (
            "http://example.com",
            {
                "all://": PROXY_URL + ":1",
                "http://": PROXY_URL + ":2",
                "all://example.com": PROXY_URL + ":3",
            },
            PROXY_URL + ":3",
        ),
        (
            "http://example.com",
            {"all://": PROXY_URL + ":1", "http://": PROXY_URL + ":2"},
            PROXY_URL + ":2",
        ),
    ],
)
def test_transport_for_request(url, proxies, expected):
    mounts = {key: httpxp.HTTPTransport(proxy=value) for key, value in proxies.items()}
    client = httpxp.Client(mounts=mounts)

    transport = client._transport_for_url(httpxp.URL(url))

    if expected is None:
        assert transport is client._transport
    else:
        assert isinstance(transport, httpxp.HTTPTransport)
        assert httpxp.URL(transport._options["proxy"]) == httpxp.URL(expected)


@pytest.mark.anyio
@pytest.mark.network
async def test_async_proxy_close():
    try:
        transport = httpxp.AsyncHTTPTransport(proxy=PROXY_URL)
        client = httpxp.AsyncClient(mounts={"https://": transport})
        await client.get("http://example.com")
    finally:
        await client.aclose()


@pytest.mark.network
def test_sync_proxy_close():
    try:
        transport = httpxp.HTTPTransport(proxy=PROXY_URL)
        client = httpxp.Client(mounts={"https://": transport})
        client.get("http://example.com")
    finally:
        client.close()


def test_unsupported_proxy_scheme():
    with pytest.raises(ValueError):
        httpxp.Client(proxy="ftp://127.0.0.1")


@pytest.mark.parametrize(
    ["url", "env", "expected"],
    [
        ("http://google.com", {}, None),
        (
            "http://google.com",
            {"HTTP_PROXY": "http://example.com"},
            "http://example.com",
        ),
        # Auto prepend http scheme
        ("http://google.com", {"HTTP_PROXY": "example.com"}, "http://example.com"),
        (
            "http://google.com",
            {"HTTP_PROXY": "http://example.com", "NO_PROXY": "google.com"},
            None,
        ),
        # Everything proxied when NO_PROXY is empty/unset
        (
            "http://127.0.0.1",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": ""},
            "http://localhost:123",
        ),
        # Not proxied if NO_PROXY matches URL.
        (
            "http://127.0.0.1",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "127.0.0.1"},
            None,
        ),
        # Proxied if NO_PROXY scheme does not match URL.
        (
            "http://127.0.0.1",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "https://127.0.0.1"},
            "http://localhost:123",
        ),
        # Proxied if NO_PROXY scheme does not match host.
        (
            "http://127.0.0.1",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "1.1.1.1"},
            "http://localhost:123",
        ),
        # Not proxied if NO_PROXY matches host domain suffix.
        (
            "http://courses.mit.edu",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "mit.edu"},
            None,
        ),
        # Proxied even though NO_PROXY matches host domain *prefix*.
        (
            "https://mit.edu.info",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "mit.edu"},
            "http://localhost:123",
        ),
        # Not proxied if one item in NO_PROXY case matches host domain suffix.
        (
            "https://mit.edu.info",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "mit.edu,edu.info"},
            None,
        ),
        # Not proxied if one item in NO_PROXY case matches host domain suffix.
        # May include whitespace.
        (
            "https://mit.edu.info",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "mit.edu, edu.info"},
            None,
        ),
        # Proxied if no items in NO_PROXY match.
        (
            "https://mit.edu.info",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "mit.edu,mit.info"},
            "http://localhost:123",
        ),
        # Proxied if NO_PROXY domain doesn't match.
        (
            "https://foo.example.com",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "www.example.com"},
            "http://localhost:123",
        ),
        # Not proxied for subdomains matching NO_PROXY, with a leading ".".
        (
            "https://www.example1.com",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": ".example1.com"},
            None,
        ),
        # Proxied, because NO_PROXY subdomains only match if "." separated.
        (
            "https://www.example2.com",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "ample2.com"},
            "http://localhost:123",
        ),
        # No requests are proxied if NO_PROXY="*" is set.
        (
            "https://www.example3.com",
            {"ALL_PROXY": "http://localhost:123", "NO_PROXY": "*"},
            None,
        ),
    ],
)
@pytest.mark.parametrize("client_class", [httpxp.Client, httpxp.AsyncClient])
def test_proxies_environ(monkeypatch, client_class, url, env, expected):
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    client = client_class()
    transport = client._transport_for_url(httpxp.URL(url))

    if expected is None:
        assert transport == client._transport
    else:
        native_transport = (
            transport._transport
            if isinstance(transport, httpxp.AsyncHTTPTransport)
            else transport
        )
        assert httpxp.URL(native_transport._options["proxy"]) == httpxp.URL(expected)


@pytest.mark.parametrize(
    ["proxies", "is_valid"],
    [
        ({"http": "http://127.0.0.1"}, False),
        ({"https": "http://127.0.0.1"}, False),
        ({"all": "http://127.0.0.1"}, False),
        ({"http://": "http://127.0.0.1"}, True),
        ({"https://": "http://127.0.0.1"}, True),
        ({"all://": "http://127.0.0.1"}, True),
    ],
)
def test_for_deprecated_proxy_params(proxies, is_valid):
    mounts = {key: httpxp.HTTPTransport(proxy=value) for key, value in proxies.items()}

    if not is_valid:
        with pytest.raises(ValueError):
            httpxp.Client(mounts=mounts)
    else:
        httpxp.Client(mounts=mounts)


def test_proxy_with_mounts():
    proxy_transport = httpxp.HTTPTransport(proxy="http://127.0.0.1")
    client = httpxp.Client(mounts={"http://": proxy_transport})

    transport = client._transport_for_url(httpxp.URL("http://example.com"))
    assert transport == proxy_transport
