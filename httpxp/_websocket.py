"""WebSocket upgrades and messages using the client's native wreq transport."""

from __future__ import annotations

import json
import typing
from dataclasses import dataclass

import anyio

from ._client import USE_CLIENT_DEFAULT, ClientState, UseClientDefault
from ._models import Request, Response
from ._transports.default import AsyncHTTPTransport, HTTPTransport
from ._types import AuthTypes, HeaderTypes, QueryParamTypes
from ._urls import URL

if typing.TYPE_CHECKING:
    from ._client import AsyncClient, Client

__all__ = ["AsyncWebSocket", "WebSocket", "WebSocketMessage", "websocket"]


@dataclass(frozen=True)
class WebSocketMessage:
    type: str
    data: str | bytes = b""
    code: int | None = None


def _message(
    value: tuple[str, list[int], int | None] | None,
) -> WebSocketMessage | None:
    if value is None:
        return None
    kind, payload, code = value
    data = bytes(payload)
    return WebSocketMessage(
        kind, data.decode() if kind in ("text", "close") else data, code
    )


def _payload(value: str | bytes | WebSocketMessage) -> tuple[str, bytes, int | None]:
    if isinstance(value, str):
        return "text", value.encode(), None
    if isinstance(value, bytes):
        return "binary", value, None
    if isinstance(value, WebSocketMessage):
        data = value.data.encode() if isinstance(value.data, str) else value.data
        return value.type, data, value.code
    raise TypeError("WebSocket messages must be str, bytes, or WebSocketMessage")


class WebSocket:
    def __init__(self, native: typing.Any, response: Response) -> None:
        self._native = native
        self.response = response
        self.protocol: str | None = native.protocol
        self._owner: Client | None = None

    def send(self, message: str | bytes | WebSocketMessage) -> None:
        self._native.send(*_payload(message))

    def send_text(self, text: str) -> None:
        self.send(text)

    def send_bytes(self, data: bytes) -> None:
        self.send(data)

    def send_json(self, value: typing.Any) -> None:
        self.send(json.dumps(value))

    def ping(self, data: bytes = b"") -> None:
        self.send(WebSocketMessage("ping", data))

    def receive(self) -> WebSocketMessage | None:
        return _message(self._native.receive())

    def __iter__(self) -> typing.Iterator[WebSocketMessage]:
        while (message := self.receive()) is not None:
            yield message
            if message.type == "close":
                break

    def close(self, code: int = 1000, reason: str = "") -> None:
        self._native.close(code, reason)
        if self._owner is not None:
            self._owner.close()
            self._owner = None

    def __enter__(self) -> WebSocket:
        return self

    def __exit__(self, *args: typing.Any) -> None:
        self.close()


class AsyncWebSocket:
    def __init__(self, native: typing.Any, response: Response) -> None:
        self._native = native
        self.response = response
        self.protocol: str | None = native.protocol

    async def send(self, message: str | bytes | WebSocketMessage) -> None:
        try:
            await anyio.to_thread.run_sync(
                self._native.send, *_payload(message), abandon_on_cancel=True
            )
        except BaseException:
            self._native.cancel()
            raise

    async def send_text(self, text: str) -> None:
        await self.send(text)

    async def send_bytes(self, data: bytes) -> None:
        await self.send(data)

    async def send_json(self, value: typing.Any) -> None:
        await self.send(json.dumps(value))

    async def ping(self, data: bytes = b"") -> None:
        await self.send(WebSocketMessage("ping", data))

    async def receive(self) -> WebSocketMessage | None:
        try:
            return _message(
                await anyio.to_thread.run_sync(
                    self._native.receive, abandon_on_cancel=True
                )
            )
        except BaseException:
            self._native.cancel()
            raise

    async def __aiter__(self) -> typing.AsyncIterator[WebSocketMessage]:
        while (message := await self.receive()) is not None:
            yield message
            if message.type == "close":
                break

    async def aclose(self, code: int = 1000, reason: str = "") -> None:
        self._native.cancel()
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(self._native.close, code, reason)

    async def __aenter__(self) -> AsyncWebSocket:
        return self

    async def __aexit__(self, *args: typing.Any) -> None:
        await self.aclose()


def _prepare(
    client: Client | AsyncClient,
    url: URL | str,
    headers: HeaderTypes | None,
    params: QueryParamTypes | None,
    extensions: typing.Mapping[str, typing.Any] | None,
    options: dict[str, typing.Any],
) -> tuple[Request, dict[str, typing.Any]]:
    if client.is_closed:
        raise RuntimeError("Cannot open a WebSocket with a closed client")
    client._state = ClientState.OPENED
    url = URL(url)
    if url.scheme in ("ws", "wss"):
        url = url.copy_with(scheme="https" if url.scheme == "wss" else "http")
    request = client.build_request(
        "GET", url, headers=headers, params=params, extensions=extensions
    )
    config = dict(request.extensions.get("private", {}))
    config.update(options)
    timeout = request.extensions.get("timeout", {})
    config.setdefault("_pool_timeout", timeout.get("pool"))
    if timeout.get("read") is not None:
        config.setdefault("read_timeout", timeout["read"])
    return request, config


def _response(native: typing.Any, request: Request) -> Response:
    return Response(
        native.status,
        headers=[(bytes(k), bytes(v)) for k, v in native.headers],
        content=b"",
        request=request,
        extensions={"http_version": native.version.encode()},
    )


def connect(
    client: Client,
    url: URL | str,
    *,
    headers: HeaderTypes | None = None,
    params: QueryParamTypes | None = None,
    auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
    extensions: typing.Mapping[str, typing.Any] | None = None,
    **options: typing.Any,
) -> WebSocket:
    request, config = _prepare(client, url, headers, params, extensions, options)
    flow = client._build_request_auth(request, auth).sync_auth_flow(request)
    try:
        request = next(flow)
        for hook in client.event_hooks["request"]:
            hook(request)
        transport = client._transport_for_url(request.url)
        if not isinstance(transport, HTTPTransport):
            raise TypeError("WebSockets require an HTTPTransport backed by wreq")
        native = transport._client.websocket(
            str(request.url), request.headers.raw, config
        )
        socket = WebSocket(native, _response(native, request))
        try:
            client.cookies.extract_cookies(socket.response)
            for hook in client.event_hooks["response"]:
                hook(socket.response)
            return socket
        except BaseException:
            socket.close()
            raise
    finally:
        flow.close()


async def connect_async(
    client: AsyncClient,
    url: URL | str,
    *,
    headers: HeaderTypes | None = None,
    params: QueryParamTypes | None = None,
    auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
    extensions: typing.Mapping[str, typing.Any] | None = None,
    **options: typing.Any,
) -> AsyncWebSocket:
    from ._native import NativeCancellation

    request, config = _prepare(client, url, headers, params, extensions, options)
    cancellation = NativeCancellation()
    config["_cancel"] = cancellation
    flow = client._build_request_auth(request, auth).async_auth_flow(request)
    try:
        request = await flow.__anext__()
        for hook in client.event_hooks["request"]:
            await hook(request)
        transport = client._transport_for_url(request.url)
        if not isinstance(transport, AsyncHTTPTransport):
            raise TypeError("WebSockets require an AsyncHTTPTransport backed by wreq")
        try:
            native = await anyio.to_thread.run_sync(
                transport._transport._client.websocket,
                str(request.url),
                request.headers.raw,
                config,
                abandon_on_cancel=True,
            )
        except BaseException:
            cancellation.cancel()
            raise
        socket = AsyncWebSocket(native, _response(native, request))
        try:
            client.cookies.extract_cookies(socket.response)
            for hook in client.event_hooks["response"]:
                await hook(socket.response)
            return socket
        except BaseException:
            await socket.aclose()
            raise
    finally:
        await flow.aclose()


def websocket(
    url: URL | str,
    *,
    privacy_options: typing.Mapping[str, typing.Any] | None = None,
    verify: typing.Any = True,
    trust_env: bool = True,
    proxy: typing.Any = None,
    **options: typing.Any,
) -> WebSocket:
    from ._client import Client

    client = Client(
        privacy_options=privacy_options, verify=verify, trust_env=trust_env, proxy=proxy
    )
    try:
        socket = client.websocket(url, **options)
    except BaseException:
        client.close()
        raise
    socket._owner = client
    return socket
