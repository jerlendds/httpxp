"""Exercise native proxy selection and tunnel headers over real sockets."""

import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
import trustme

import httpxp


@pytest.fixture
def proxy_server():
    ca = trustme.CA()
    certificate = ca.issue_cert("destination.invalid")
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    certificate.configure_cert(tls)
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(
                {"path": self.path, "headers": dict(self.headers)}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_CONNECT(self):
            captured.append((self.path, dict(self.headers)))
            self.send_response(200, "Connection established")
            self.end_headers()
            self.wfile.flush()
            self.connection = tls.wrap_socket(self.connection, server_side=True)
            self.rfile = self.connection.makefile("rb")
            self.wfile = self.connection.makefile("wb")
            self.handle_one_request()
            self.close_connection = True

        def finish(self):
            try:
                super().finish()
            finally:
                self.connection.close()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = ssl.create_default_context()
    ca.configure_trust(context)
    try:
        yield f"http://127.0.0.1:{server.server_port}", context, captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_native_proxy_basic_auth(proxy_server):
    url, _, _ = proxy_server
    with httpxp.Client(
        trust_env=False,
        privacy_options={"proxy": {"url": url, "basic_auth": ("user", "password")}},
    ) as client:
        result = client.get("http://destination.invalid/example?q=1").json()
    assert result["path"] == "http://destination.invalid/example?q=1"
    headers = httpxp.Headers(result["headers"])
    assert headers["Proxy-Authorization"] == "Basic dXNlcjpwYXNzd29yZA=="


@pytest.mark.parametrize("public_proxy", [False, True])
def test_native_proxy_tunnel_headers(proxy_server, public_proxy):
    url, context, captured = proxy_server
    options: dict[str, Any] = (
        {"proxy": httpxp.Proxy(url, headers={"X-Proxy-Token": "secret"})}
        if public_proxy
        else {
            "privacy_options": {
                "proxy": {
                    "url": url,
                    "scheme": "https",
                    "custom_http_auth": "Bearer secret",
                    "custom_http_headers": [("X-Proxy-Token", "secret")],
                }
            }
        }
    )
    with httpxp.Client(trust_env=False, verify=context, **options) as client:
        result = client.get("https://destination.invalid/example").json()
    assert captured[0][0] == "destination.invalid:443"
    tunnel_headers = httpxp.Headers(captured[0][1])
    assert tunnel_headers["X-Proxy-Token"] == "secret"
    if not public_proxy:
        assert tunnel_headers["Proxy-Authorization"] == "Bearer secret"
    origin_headers = httpxp.Headers(result["headers"])
    assert "X-Proxy-Token" not in origin_headers
    assert "Proxy-Authorization" not in origin_headers
    assert result["path"] == "/example"


@pytest.mark.anyio
async def test_native_request_proxy(proxy_server):
    url, _, _ = proxy_server
    async with httpxp.AsyncClient(trust_env=False) as client:
        response = await client.get(
            "http://destination.invalid/request",
            extensions={"private": {"proxy": {"url": url}}},
        )
    assert response.json()["path"] == "http://destination.invalid/request"


def test_native_proxy_exclusion(proxy_server):
    url, _, _ = proxy_server
    with httpxp.Client(
        trust_env=False,
        privacy_options={
            "proxy": {"url": "http://127.0.0.1:1", "no_proxy": "127.0.0.1"},
            "local_addresses": ("127.0.0.1", None),
        },
    ) as client:
        response = client.get(url + "/direct")
    assert response.json()["path"] == "/direct"


def test_native_proxy_scheme_selection(proxy_server):
    url, _, _ = proxy_server
    with httpxp.Client(
        trust_env=False,
        privacy_options={
            "proxies": [
                {"url": "http://127.0.0.1:1", "scheme": "https"},
                {"url": url, "scheme": "http"},
            ]
        },
    ) as client:
        response = client.get("http://destination.invalid/selected")
    assert response.json()["path"] == "http://destination.invalid/selected"


@pytest.fixture
def socks_server():
    import socket
    import socketserver

    captured = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            version, count = self.rfile.read(2)
            assert version == 5
            assert 2 in self.rfile.read(count)
            self.wfile.write(b"\x05\x02")
            assert self.rfile.read(1) == b"\x01"
            username = self.rfile.read(self.rfile.read(1)[0])
            password = self.rfile.read(self.rfile.read(1)[0])
            self.wfile.write(b"\x01\x00")
            version, command, reserved, address_type = self.rfile.read(4)
            assert (version, command, reserved) == (5, 1, 0)
            if address_type == 3:
                address = self.rfile.read(self.rfile.read(1)[0]).decode()
            else:
                assert address_type == 1
                address = socket.inet_ntop(socket.AF_INET, self.rfile.read(4))
            port = int.from_bytes(self.rfile.read(2), "big")
            captured.append((username, password, address_type, address, port))
            self.wfile.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50")
            request_line = self.rfile.readline()
            assert request_line == b"GET /socks HTTP/1.1\r\n"
            while self.rfile.readline() not in (b"\r\n", b""):
                pass
            self.wfile.write(
                b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n"
                b"Connection: close\r\n\r\nsocks"
            )

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "scheme,host,address_type",
    [("socks5h", "destination.invalid", 3), ("socks5", "127.0.0.1", 1)],
)
def test_native_socks_auth_and_resolution(socks_server, scheme, host, address_type):
    port, captured = socks_server
    with httpxp.Client(
        trust_env=False,
        proxy=f"{scheme}://user:password@127.0.0.1:{port}",
    ) as client:
        assert client.get(f"http://{host}:8080/socks").text == "socks"
    assert captured == [(b"user", b"password", address_type, host, 8080)]


@pytest.mark.parametrize("request_proxy", [False, True])
def test_native_unix_proxy(tmp_path, request_proxy):
    import socketserver
    import sys

    if sys.platform == "win32":
        pytest.skip("Unix domain sockets required")
    socket_path = str(tmp_path / "proxy.sock")

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            assert self.rfile.readline() == b"GET /containers HTTP/1.1\r\n"
            while self.rfile.readline() not in (b"\r\n", b""):
                pass
            self.wfile.write(
                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n[]"
            )

    server = socketserver.UnixStreamServer(socket_path, Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    proxy = {"url": socket_path, "scheme": "unix"}
    try:
        with httpxp.Client(
            trust_env=False,
            privacy_options={} if request_proxy else {"proxy": proxy},
        ) as client:
            response = client.get(
                "http://destination.invalid/containers",
                extensions={"private": {"proxy": proxy}} if request_proxy else {},
            )
        assert response.json() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("request_proxy", [False, True])
def test_proxy_example(proxy_server, monkeypatch, capsys, request_proxy):
    from examples.private_proxy import main

    url, _, _ = proxy_server
    argv = ["private_proxy.py", "http://destination.invalid/example", url]
    if request_proxy:
        argv.append("--request-proxy")
    monkeypatch.setattr("sys.argv", argv)
    main()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Status: 200"
    assert json.loads(lines[1])["path"] == "http://destination.invalid/example"
