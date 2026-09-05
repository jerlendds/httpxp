"""Tests against the real native transport (no mocked network backend)."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import AsyncIterator, Iterator

import pytest

import httpxp


@pytest.fixture
def wreq_server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            body = b"hello wreq"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Peer-Port", str(self.client_address[1]))
            self.send_header(
                "X-Request-Transfer-Encoding",
                self.headers.get("Transfer-Encoding", "none"),
            )
            self.end_headers()
            self.wfile.write(body)

        do_OPTIONS = do_GET
        do_DELETE = do_GET

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_native_sync(wreq_server):
    with httpxp.Client(
        trust_env=False, privacy_options={"tcp_nodelay": True}
    ) as client:
        response = client.get(wreq_server)
        assert response.status_code == 200
        assert response.text == "hello wreq"
        assert response.http_version == "HTTP/1.1"
        assert client.post(wreq_server, json={"hello": "world"}).json() == {
            "hello": "world"
        }
        with client.stream("GET", wreq_server) as response:
            assert not response.is_stream_consumed
            assert b"".join(response.iter_bytes()) == b"hello wreq"


@pytest.mark.anyio
async def test_native_async(wreq_server):
    async with httpxp.AsyncClient(trust_env=False) as client:
        response = await client.get(wreq_server)
        assert response.status_code == 200
        assert response.text == "hello wreq"
        response = await client.post(wreq_server, data={"one": "1"})
        assert response.content == b"one=1"
        async with client.stream("GET", wreq_server) as response:
            assert not response.is_stream_consumed
            assert (
                b"".join([chunk async for chunk in response.aiter_bytes()])
                == b"hello wreq"
            )


def test_unknown_option():
    with pytest.raises(ValueError, match="unknown client option"):
        httpxp.Client(trust_env=False, privacy_options={"does_not_exist": True})


def test_top_level_options(wreq_server):
    response = httpxp.get(
        wreq_server,
        trust_env=False,
        privacy_options={"tcp_linger": 0},
        extensions={"private": {"version": "1.1", "local_address": "127.0.0.1"}},
    )
    assert response.text == "hello wreq"


def test_custom_emulation(wreq_server):
    emulation = {
        "tls_options": {
            "enable_ocsp_stapling": True,
            "curves_list": "X25519:P-256:P-384",
            "cipher_list": (
                "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:"
                "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256:"
                "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256"
            ),
            "sigalgs_list": "ecdsa_secp256r1_sha256:rsa_pss_rsae_sha256",
            "alpn_protocols": ["h2", "http/1.1"],
            "min_tls_version": "1.2",
            "max_tls_version": "1.3",
        },
        "http2_options": {
            "initial_stream_id": 3,
            "initial_window_size": 16777216,
            "initial_connection_window_size": 16711681 + 65535,
            "headers_pseudo_order": ["method", "path", "authority", "scheme"],
        },
        "orig_headers": ["User-Agent", "Accept-Language", "Accept-Encoding"],
        "headers": [("User-Agent", "TwitterAndroid/10.89.0-release.0")],
    }
    with httpxp.Client(
        trust_env=False, privacy_options={"emulation": emulation}
    ) as client:
        assert client.get(wreq_server).status_code == 200
        assert (
            client.get(
                wreq_server, extensions={"private": {"emulation": emulation}}
            ).status_code
            == 200
        )


def test_tls_certificate_store(tmp_path):
    import ssl

    import trustme

    ca = trustme.CA()
    certificate = ca.issue_cert("localhost")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    certificate.configure_cert(context)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("X-Session-Reused", str(self.connection.session_reused))
            self.end_headers()
            self.wfile.write(b"TLS through BoringSSL")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"https://localhost:{server.server_port}"
    try:
        with pytest.raises(httpxp.ConnectError):
            httpxp.get(url, trust_env=False)
        response = httpxp.get(
            url, trust_env=False, verify=False, privacy_options={"tls_info": True}
        )
        assert response.text == "TLS through BoringSSL"
        assert response.extensions["tls_info"]["peer_certificate"].startswith(b"0")
        response = httpxp.get(
            url,
            trust_env=False,
            privacy_options={"tls_cert_store_pem": ca.cert_pem.bytes()},
        )
        assert response.status_code == 200
        keylog = tmp_path / "tls-keys.log"
        with httpxp.Client(
            trust_env=False,
            privacy_options={
                "tls_cert_store_pem": ca.cert_pem.bytes(),
                "tls_keylog": str(keylog),
                "tls_session_cache": 2,
                "tls_options": {"pre_shared_key": True, "session_ticket": True},
            },
        ) as client:
            assert client.get(url).headers["X-Session-Reused"] == "False"
            assert client.get(url).headers["X-Session-Reused"] == "True"
        assert any(
            line.startswith("CLIENT_RANDOM ")
            for line in keylog.read_text().splitlines()
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def upload_server():
    received = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            body = bytearray()
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                size = int(line.strip(), 16)
                if not size:
                    self.rfile.readline()
                    break
                body.extend(self.rfile.read(size))
                self.rfile.read(2)
                received.set()
                if self.path == "/reject":
                    self.send_response(413)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_streaming_upload_backpressure(upload_server):
    url, received = upload_server

    def chunks() -> Iterator[bytes]:
        yield b"first"
        assert received.wait(2), "request body was buffered before sending"
        yield b"second"

    response = httpxp.post(url, content=chunks(), trust_env=False)
    assert response.content == b"firstsecond"


@pytest.mark.anyio
async def test_async_streaming_upload_backpressure(upload_server):
    import anyio

    url, received = upload_server

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first"
        assert await anyio.to_thread.run_sync(received.wait, 2)
        yield b"second"

    async with httpxp.AsyncClient(trust_env=False) as client:
        response = await client.post(url, content=chunks())
        assert response.content == b"firstsecond"


def test_upload_exception_propagates(upload_server):
    url, _ = upload_server

    def chunks() -> Iterator[bytes]:
        yield b"first"
        raise LookupError("upload source failed")

    with pytest.raises(LookupError, match="upload source failed"):
        httpxp.post(url, content=chunks(), trust_env=False)


@pytest.mark.anyio
async def test_async_upload_exception_propagates(upload_server):
    url, _ = upload_server

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first"
        raise LookupError("async upload source failed")

    async with httpxp.AsyncClient(trust_env=False) as client:
        with pytest.raises(LookupError, match="async upload source failed"):
            await client.post(url, content=chunks())


@pytest.fixture
def cancellation_server():
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            try:
                if self.path == "/headers":
                    release.wait(5)
                self.send_response(200)
                self.send_header("Content-Length", "4")
                self.end_headers()
                if self.path == "/body":
                    self.wfile.write(b"d")
                    self.wfile.flush()
                    release.wait(5)
                    self.wfile.write(b"one")
                else:
                    self.wfile.write(b"done")
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["headers", "body", "pool"])
async def test_cancellation_releases_request(cancellation_server, phase):
    import anyio

    async with httpxp.AsyncClient(
        trust_env=False, timeout=None, limits=httpxp.Limits(max_connections=1)
    ) as client:
        if phase == "pool":
            async with client.stream("GET", cancellation_server + "/body"):
                with pytest.raises(TimeoutError), anyio.fail_after(0.05):
                    await client.get(cancellation_server)
        else:
            with pytest.raises(TimeoutError), anyio.fail_after(0.05):
                await client.get(cancellation_server + "/" + phase)
        with anyio.fail_after(2):
            response = await client.get(cancellation_server)
        assert response.content == b"done"


@pytest.mark.anyio
async def test_cancellation_closes_async_upload(upload_server):
    import anyio

    url, _ = upload_server
    closed = anyio.Event()

    async def chunks() -> AsyncIterator[bytes]:
        try:
            yield b"first"
            await anyio.sleep_forever()
        finally:
            closed.set()

    async with httpxp.AsyncClient(trust_env=False, timeout=None) as client:
        with pytest.raises(TimeoutError), anyio.fail_after(0.1):
            await client.post(url, content=chunks())
        with anyio.fail_after(1):
            await closed.wait()


@pytest.mark.anyio
async def test_early_response_closes_async_upload(upload_server):
    import anyio

    url, _ = upload_server
    closed = anyio.Event()

    async def chunks() -> AsyncIterator[bytes]:
        try:
            yield b"first"
            await anyio.sleep_forever()
        finally:
            closed.set()

    async with httpxp.AsyncClient(trust_env=False, timeout=None) as client:
        with anyio.fail_after(2):
            response = await client.post(url + "/reject", content=chunks())
        assert response.status_code == 413
        assert closed.is_set()


@pytest.fixture
def delayed_listener():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler, bind_and_activate=False)
    server.server_bind()
    ready = threading.Event()

    def serve():
        ready.wait(0.15)
        server.server_activate()
        server.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        ready.set()
        server.shutdown()
        server.server_close()
        thread.join()


def test_connection_retries_preserve_upload(delayed_listener):
    yielded = []

    def chunks() -> Iterator[bytes]:
        yielded.append(True)
        yield b"retry"

    transport = httpxp.HTTPTransport(retries=2, trust_env=False)
    with httpxp.Client(transport=transport) as client:
        response = client.post(
            delayed_listener, content=chunks(), headers={"Content-Length": "5"}
        )
    assert response.content == b"retry"
    assert yielded == [True]


@pytest.mark.anyio
async def test_async_connection_retries_preserve_upload(delayed_listener):
    yielded = []

    async def chunks() -> AsyncIterator[bytes]:
        yielded.append(True)
        yield b"retry"

    transport = httpxp.AsyncHTTPTransport(retries=2, trust_env=False)
    async with httpxp.AsyncClient(transport=transport) as client:
        response = await client.post(
            delayed_listener, content=chunks(), headers={"Content-Length": "5"}
        )
    assert response.content == b"retry"
    assert yielded == [True]


@pytest.mark.anyio
async def test_empty_requests_do_not_start_upload_stream(wreq_server):
    async with httpxp.AsyncClient(trust_env=False) as client:
        for method in ("GET", "OPTIONS", "DELETE") * 4:
            response = await client.request(method, wreq_server)
            assert response.status_code == 200
            assert response.headers["X-Request-Transfer-Encoding"] == "none"
            assert response.content == b"hello wreq"


@pytest.mark.anyio
async def test_early_response_keeps_response_readable(server):
    import anyio

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first"
        await anyio.sleep_forever()

    async with httpxp.AsyncClient(trust_env=False, timeout=None) as client:
        for _ in range(5):
            with anyio.fail_after(2):
                response = await client.post(server.url, content=chunks())
            assert response.status_code == 200
            assert response.text == "Hello, world!"


def test_dns_callback(wreq_server):
    calls = []
    port = httpxp.URL(wreq_server).port

    def resolve(host):
        calls.append(host)
        return [("127.0.0.1", port)]

    with httpxp.Client(
        trust_env=False, privacy_options={"dns_resolver": resolve}
    ) as client:
        assert client.get("http://resolver.invalid").text == "hello wreq"
    assert calls == ["resolver.invalid"]


@pytest.mark.anyio
async def test_dns_callback_async_client(wreq_server):
    port = httpxp.URL(wreq_server).port
    async with httpxp.AsyncClient(
        trust_env=False,
        privacy_options={"dns_resolver": lambda host: [("127.0.0.1", port)]},
    ) as client:
        assert (await client.get("http://resolver.invalid")).text == "hello wreq"


def test_dns_callback_exception():
    failure = RuntimeError("resolver failed")

    def resolve(host):
        raise failure

    with httpxp.Client(
        trust_env=False, privacy_options={"dns_resolver": resolve}
    ) as client:
        with pytest.raises(RuntimeError) as caught:
            client.get("http://resolver.invalid")
    assert caught.value is failure


def test_dns_static_override_precedes_callback(wreq_server):
    def resolve(host):
        raise AssertionError("static override should bypass callback")

    address = str(httpxp.URL(wreq_server).netloc.decode())
    with httpxp.Client(
        trust_env=False,
        privacy_options={
            "dns_resolver": resolve,
            "resolve": {"resolver.invalid": [address]},
        },
    ) as client:
        assert client.get("http://resolver.invalid").text == "hello wreq"


@pytest.mark.parametrize("addresses", [[("not-an-ip", 80)], [("127.0.0.1", -1)]])
def test_dns_invalid_result(addresses):
    with httpxp.Client(
        trust_env=False, privacy_options={"dns_resolver": lambda host: addresses}
    ) as client:
        with pytest.raises((ValueError, OverflowError)):
            client.get("http://resolver.invalid")


def test_dns_timeout():
    release = threading.Event()

    def resolve(host):
        release.wait(5)
        return [("127.0.0.1", 80)]

    try:
        with httpxp.Client(
            trust_env=False,
            privacy_options={"dns_resolver": resolve, "connect_timeout": 0.05},
        ) as client:
            with pytest.raises(httpxp.ConnectTimeout):
                client.get("http://resolver.invalid")
    finally:
        release.set()


@pytest.mark.anyio
async def test_dns_cancellation_releases_pool(wreq_server):
    import anyio

    started = threading.Event()
    release = threading.Event()

    def resolve(host):
        started.set()
        release.wait(5)
        return [("127.0.0.1", 80)]

    try:
        async with httpxp.AsyncClient(
            trust_env=False,
            limits=httpxp.Limits(max_connections=1),
            privacy_options={"dns_resolver": resolve},
        ) as client:
            with anyio.fail_after(2):
                async with anyio.create_task_group() as group:
                    group.start_soon(client.get, "http://resolver.invalid")
                    assert await anyio.to_thread.run_sync(started.wait, 1)
                    group.cancel_scope.cancel()
                assert (await client.get(wreq_server)).text == "hello wreq"
    finally:
        release.set()


@pytest.mark.parametrize("first,second", [("one", "two"), (1, 2), ("1", 1)])
def test_request_group_isolates_connections(wreq_server, first, second):
    with httpxp.Client(trust_env=False) as client:

        def peer(group: str | int) -> str:
            return client.get(
                wreq_server, extensions={"private": {"group": group}}
            ).headers["X-Peer-Port"]

        first_port = peer(first)
        assert peer(first) == first_port
        assert peer(second) != first_port
        assert peer(first) == first_port
