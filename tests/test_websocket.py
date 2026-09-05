"""Real WebSocket frames sent through the Rust wreq upgrade path."""

import base64
import hashlib
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

import anyio
import pytest

import httpxp


def read_frame(reader: Any) -> tuple[int, bytes] | None:
    head = reader.read(2)
    if not head:
        return None
    opcode = head[0] & 15
    length = head[1] & 127
    if length == 126:
        length = struct.unpack("!H", reader.read(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", reader.read(8))[0]
    mask = reader.read(4) if head[1] & 128 else None
    payload = reader.read(length)
    if mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def write_frame(writer: Any, opcode: int, payload: bytes) -> None:
    header = bytes([0x80 | opcode])
    if len(payload) < 126:
        header += bytes([len(payload)])
    elif len(payload) < 65536:
        header += bytes([126]) + struct.pack("!H", len(payload))
    else:
        header += bytes([127]) + struct.pack("!Q", len(payload))
    writer.write(header + payload)
    writer.flush()


@pytest.fixture
def websocket_server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            key = self.headers.get("Sec-WebSocket-Key")
            if not key:
                self.send_response(400)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            accept = base64.b64encode(
                hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
                ).digest()
            ).decode()
            self.send_response(101)
            self.send_header("Connection", "Upgrade")
            self.send_header("Upgrade", "websocket")
            self.send_header("Sec-WebSocket-Accept", accept)
            if self.headers.get("Sec-WebSocket-Protocol"):
                self.send_header(
                    "Sec-WebSocket-Protocol",
                    self.headers["Sec-WebSocket-Protocol"].split(",")[0].strip(),
                )
            self.send_header("X-Request-Path", self.path)
            self.send_header("X-Request-Auth", self.headers.get("Authorization", ""))
            self.send_header("X-Request-Cookie", self.headers.get("Cookie", ""))
            self.send_header("Set-Cookie", "websocket=opened; Path=/")
            self.end_headers()
            self.close_connection = True
            try:
                while (frame := read_frame(self.rfile)) is not None:
                    opcode, payload = frame
                    write_frame(self.wfile, 10 if opcode == 9 else opcode, payload)
                    if opcode == 8:
                        break
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"ws://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_websocket_sync(websocket_server):
    with httpxp.Client(
        trust_env=False, auth=("user", "pass"), cookies={"session": "one"}
    ) as client:
        with client.websocket(
            websocket_server,
            params={"q": "hello"},
            protocols=["echo"],
            read_buffer_size=1024 * 1024,
        ) as socket:
            assert socket.response.status_code == 101
            assert socket.response.http_version == "HTTP/1.1"
            assert socket.protocol == "echo"
            assert socket.response.headers["X-Request-Path"] == "/?q=hello"
            assert socket.response.headers["X-Request-Auth"] == "Basic dXNlcjpwYXNz"
            assert socket.response.headers["X-Request-Cookie"] == "session=one"
            assert client.cookies["websocket"] == "opened"
            socket.send_text("hello")
            assert socket.receive() == httpxp.WebSocketMessage("text", "hello")
            socket.send_bytes(b"\x00\xff" * 4096)
            assert socket.receive() == httpxp.WebSocketMessage(
                "binary", b"\x00\xff" * 4096
            )
            socket.ping(b"ping")
            assert socket.receive() == httpxp.WebSocketMessage("pong", b"ping")


def test_websocket_top_level(websocket_server):
    with httpxp.websocket(websocket_server, trust_env=False) as socket:
        socket.send_json({"hello": "world"})
        assert socket.receive() == httpxp.WebSocketMessage("text", '{"hello": "world"}')


@pytest.mark.anyio
async def test_websocket_async(websocket_server):
    async with httpxp.AsyncClient(trust_env=False) as client:
        async with await client.websocket(
            websocket_server, protocols=["echo"]
        ) as socket:
            await socket.send("hello async")
            assert await socket.receive() == httpxp.WebSocketMessage(
                "text", "hello async"
            )
            await socket.send(b"binary")
            assert await socket.receive() == httpxp.WebSocketMessage(
                "binary", b"binary"
            )


@pytest.mark.anyio
async def test_websocket_concurrent_send_receive(websocket_server):
    async with httpxp.AsyncClient(trust_env=False) as client:
        async with await client.websocket(websocket_server) as socket:
            messages = []
            ready = anyio.Event()

            async def receive():
                ready.set()
                messages.append(await socket.receive())

            with anyio.fail_after(2):
                async with anyio.create_task_group() as group:
                    group.start_soon(receive)
                    await ready.wait()
                    await socket.send("concurrent")
            assert messages == [httpxp.WebSocketMessage("text", "concurrent")]


@pytest.mark.anyio
async def test_websocket_cancel_releases_pool(websocket_server):
    async with httpxp.AsyncClient(
        trust_env=False, limits=httpxp.Limits(max_connections=1)
    ) as client:
        socket = await client.websocket(websocket_server)
        try:
            with pytest.raises(TimeoutError), anyio.fail_after(0.05):
                await socket.receive()
        finally:
            await socket.aclose()
        with anyio.fail_after(2):
            async with await client.websocket(websocket_server) as second:
                await second.send("after cancellation")
                assert await second.receive() == httpxp.WebSocketMessage(
                    "text", "after cancellation"
                )


@pytest.fixture
def http2_websocket_server():
    import io
    import socketserver
    import ssl

    import h2.config
    import h2.connection
    import h2.events
    import h2.settings
    import trustme

    ca = trustme.CA()
    certificate = ca.issue_cert("localhost")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    certificate.configure_cert(context)
    context.set_alpn_protocols(["h2"])
    requests = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            connection = h2.connection.H2Connection(
                config=h2.config.H2Configuration(
                    client_side=False, header_encoding="utf-8"
                )
            )
            connection.initiate_connection()
            connection.update_settings(
                {h2.settings.SettingCodes.ENABLE_CONNECT_PROTOCOL: 1}
            )
            self.request.sendall(connection.data_to_send())
            pending = {}
            try:
                while data := self.request.recv(65536):
                    for event in connection.receive_data(data):
                        if isinstance(event, h2.events.RequestReceived):
                            request_headers = cast(dict[str, str], dict(event.headers))
                            requests.append(request_headers)
                            pending[event.stream_id] = bytearray()
                            headers = [(":status", "200")]
                            protocol = request_headers.get("sec-websocket-protocol")
                            if protocol:
                                headers.append(
                                    (
                                        "sec-websocket-protocol",
                                        protocol.split(",")[0].strip(),
                                    )
                                )
                            connection.send_headers(event.stream_id, headers)
                        elif isinstance(event, h2.events.DataReceived):
                            connection.acknowledge_received_data(
                                event.flow_controlled_length, event.stream_id
                            )
                            buffer = pending[event.stream_id]
                            buffer.extend(event.data)
                            while len(buffer) >= 2:
                                size = buffer[1] & 127
                                prefix = 2
                                if size == 126:
                                    if len(buffer) < 4:
                                        break
                                    size = struct.unpack("!H", buffer[2:4])[0]
                                    prefix = 4
                                elif size == 127:
                                    if len(buffer) < 10:
                                        break
                                    size = struct.unpack("!Q", buffer[2:10])[0]
                                    prefix = 10
                                total = prefix + (4 if buffer[1] & 128 else 0) + size
                                if len(buffer) < total:
                                    break
                                frame = read_frame(io.BytesIO(bytes(buffer[:total])))
                                assert frame is not None
                                opcode, payload = frame
                                del buffer[:total]
                                output = io.BytesIO()
                                write_frame(
                                    output, 10 if opcode == 9 else opcode, payload
                                )
                                connection.send_data(
                                    event.stream_id,
                                    output.getvalue(),
                                    end_stream=opcode == 8,
                                )
                    outgoing = connection.data_to_send()
                    if outgoing:
                        self.request.sendall(outgoing)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    server = Server(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"wss://localhost:{server.server_address[1]}",
            ca.cert_pem.bytes(),
            requests,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_websocket_http2(http2_websocket_server):
    url, ca, requests = http2_websocket_server
    with httpxp.Client(
        http1=False,
        http2=True,
        trust_env=False,
        privacy_options={"tls_cert_store_pem": ca},
    ) as client:
        with client.websocket(
            url, version="2", protocols=["echo"], read_buffer_size=1024 * 1024
        ) as socket:
            assert socket.response.status_code == 200
            assert socket.response.http_version == "HTTP/2"
            assert socket.protocol == "echo"
            socket.send("Hello HTTP/2")
            assert socket.receive() == httpxp.WebSocketMessage("text", "Hello HTTP/2")
    assert requests[0][":method"] == "CONNECT"
    assert requests[0][":protocol"] == "websocket"
    assert "sec-websocket-key" not in requests[0]


@pytest.mark.anyio
async def test_websocket_http2_async(http2_websocket_server):
    url, ca, requests = http2_websocket_server
    async with httpxp.AsyncClient(
        http1=False,
        http2=True,
        trust_env=False,
        privacy_options={"tls_cert_store_pem": ca},
    ) as client:
        async with await client.websocket(url, version="2") as socket:
            await socket.send(b"HTTP2 bytes")
            assert await socket.receive() == httpxp.WebSocketMessage(
                "binary", b"HTTP2 bytes"
            )
    assert requests[0][":protocol"] == "websocket"


@pytest.mark.parametrize(
    "options",
    [
        {"read_buffer_size": 0},
        {"write_buffer_size": 1024, "max_write_buffer_size": 1024},
        {"max_message_size": -1},
        {"unknown_websocket_option": True},
    ],
)
def test_invalid_websocket_options(websocket_server, options):
    with httpxp.Client(trust_env=False) as client:
        with pytest.raises((ValueError, OverflowError)):
            client.websocket(websocket_server, **options)


def test_websocket_message_limit(websocket_server):
    with httpxp.Client(trust_env=False) as client:
        with client.websocket(websocket_server, max_message_size=8) as socket:
            socket.send("larger than eight bytes")
            with pytest.raises(httpxp.ReadError):
                socket.receive()


def test_websocket_close_frame(websocket_server):
    with httpxp.Client(trust_env=False) as client:
        with client.websocket(websocket_server) as socket:
            socket.send(httpxp.WebSocketMessage("close", "finished", 1000))
            assert socket.receive() == httpxp.WebSocketMessage(
                "close", "finished", 1000
            )


def test_websocket_closed_client(websocket_server):
    client = httpxp.Client(trust_env=False)
    client.close()
    with pytest.raises(RuntimeError, match="closed client"):
        client.websocket(websocket_server)


@pytest.mark.parametrize("http2", [False, True])
@pytest.mark.parametrize("async_client", [False, True])
def test_websocket_example(request, monkeypatch, tmp_path, capsys, http2, async_client):
    from examples.private_websocket import main

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    if http2:
        url, ca, _ = request.getfixturevalue("http2_websocket_server")
        ca_path = tmp_path / "ca.pem"
        ca_path.write_bytes(ca)
        argv = ["private_websocket.py", url, "--http2", "--ca", str(ca_path)]
    else:
        argv = ["private_websocket.py", request.getfixturevalue("websocket_server")]
    if async_client:
        argv.append("--async-client")
    monkeypatch.setattr("sys.argv", argv)
    main()
    output = capsys.readouterr().out.splitlines()
    assert output[0].startswith("HTTP/2" if http2 else "HTTP/1.1")
    assert output[1:] == [f"Hello, World! #{i}" for i in range(1, 11)]
