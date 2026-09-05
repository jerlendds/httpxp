"""Synchronous and asynchronous transports backed by Rust wreq."""

from __future__ import annotations

import ssl
import time
import typing
from pathlib import Path

import anyio
from anyio.from_thread import BlockingPortal

from .._config import DEFAULT_LIMITS, Limits, Proxy, create_ssl_context
from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    RequestNotRead,
    UnsupportedProtocol,
)
from .._models import Request, Response
from .._types import AsyncByteStream, CertTypes, ProxyTypes, SyncByteStream
from .._urls import URL
from .base import AsyncBaseTransport, BaseTransport

SOCKET_OPTION = typing.Union[
    typing.Tuple[int, int, int],
    typing.Tuple[int, int, typing.Union[bytes, bytearray]],
    typing.Tuple[int, int, None, int],
]
__all__ = ["AsyncHTTPTransport", "HTTPTransport"]


def _options(
    verify: ssl.SSLContext | str | bool,
    cert: CertTypes | None,
    trust_env: bool,
    http1: bool,
    http2: bool,
    limits: Limits,
    proxy: ProxyTypes | None,
    uds: str | None,
    local_address: str | None,
    socket_options: typing.Iterable[SOCKET_OPTION] | None,
    privacy_options: typing.Mapping[str, typing.Any] | None,
) -> dict[str, typing.Any]:
    if socket_options:
        raise ValueError("Use privacy_options TCP settings instead of socket_options")
    if not http1 and not http2:
        raise ValueError("At least one HTTP version must be enabled")
    context = create_ssl_context(verify=verify, cert=cert, trust_env=trust_env)
    opts: dict[str, typing.Any] = {
        "tls_cert_verification": context.verify_mode != ssl.CERT_NONE,
        "tls_verify_hostname": context.check_hostname,
        "pool_idle_timeout": limits.keepalive_expiry,
        "_max_connections": limits.max_connections,
    }
    if context.verify_mode != ssl.CERT_NONE:
        opts["tls_cert_store"] = context.get_ca_certs(binary_form=True)
    if cert is not None:
        if isinstance(cert, str):
            pem = Path(cert).read_bytes()
            opts["tls_identity"] = (pem, pem)
        else:
            opts["tls_identity"] = (
                Path(cert[0]).read_bytes(),
                Path(cert[1]).read_bytes(),
            )
    if limits.max_keepalive_connections is not None:
        opts["pool_max_idle_per_host"] = limits.max_keepalive_connections
    if limits.max_connections is not None:
        opts["pool_max_size"] = limits.max_connections
    if not http2:
        opts["http1_only"] = True
    elif not http1:
        opts["http2_only"] = True
    if local_address is not None:
        opts["local_address"] = local_address
    if uds is not None:
        opts["uds"] = uds
    proxy = Proxy(url=proxy) if isinstance(proxy, (str, URL)) else proxy
    if proxy is not None:
        url = proxy.url
        if proxy.raw_auth:
            url = url.copy_with(
                username=proxy.raw_auth[0].decode(), password=proxy.raw_auth[1].decode()
            )
        opts["proxy"] = (
            {"url": str(url), "custom_http_headers": proxy.headers.raw}
            if proxy.headers
            else str(url)
        )
    opts.update(privacy_options or {})
    return opts


def _request_options(request: Request) -> dict[str, typing.Any]:
    if request.url.scheme not in ("http", "https"):
        raise UnsupportedProtocol(
            f"Request URL has an unsupported protocol {request.url.scheme + '://'!r}."
        )
    opts = {}
    timeout = request.extensions.get("timeout", {})
    if timeout.get("read") is not None:
        opts["read_timeout"] = timeout["read"]
    opts["_pool_timeout"] = timeout.get("pool")
    opts["_write_timeout"] = timeout.get("write")
    opts.update(request.extensions.get("private", {}))
    return opts


def _request_body(
    request: Request, stream: typing.Iterator[bytes]
) -> bytes | typing.Iterator[bytes] | None:
    try:
        return request.content or None
    except RequestNotRead:
        return stream


def _response(native: typing.Any, stream: SyncByteStream | AsyncByteStream) -> Response:
    extensions: dict[str, typing.Any] = {"http_version": native.version.encode()}
    if native.peer_certificate is not None:
        extensions["tls_info"] = {"peer_certificate": bytes(native.peer_certificate)}
    return Response(
        native.status,
        headers=[(bytes(k), bytes(v)) for k, v in native.headers],
        stream=stream,
        extensions=extensions,
    )


class ResponseStream(SyncByteStream):
    def __init__(self, native: typing.Any) -> None:
        self._native = native

    def __iter__(self) -> typing.Iterator[bytes]:
        while (chunk := self._native.read_chunk()) is not None:
            yield chunk

    def close(self) -> None:
        self._native.close()


class HTTPTransport(BaseTransport):
    def __init__(
        self,
        verify: ssl.SSLContext | str | bool = True,
        cert: CertTypes | None = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        proxy: ProxyTypes | None = None,
        uds: str | None = None,
        local_address: str | None = None,
        retries: int = 0,
        socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
        *,
        privacy_options: typing.Mapping[str, typing.Any] | None = None,
    ) -> None:
        from .._native import NativeClient

        self._options = _options(
            verify,
            cert,
            trust_env,
            http1,
            http2,
            limits,
            proxy,
            uds,
            local_address,
            socket_options,
            privacy_options,
        )
        if not isinstance(retries, int) or retries < 0:
            raise ValueError("retries must be a non-negative integer")
        self._client = NativeClient(self._options)
        self._retries = retries

    def handle_request(self, request: Request) -> Response:
        assert isinstance(request.stream, SyncByteStream)
        body = _request_body(request, iter(request.stream))
        options = _request_options(request)
        for attempt in range(self._retries + 1):
            if attempt > 1:
                time.sleep(0.5 * 2 ** (attempt - 2))
            try:
                native = self._client.send(
                    request.method,
                    str(request.url),
                    request.headers.raw,
                    body,
                    options,
                )
                break
            except (ConnectError, ConnectTimeout):
                if attempt == self._retries:
                    raise
        return _response(native, ResponseStream(native))

    def close(self) -> None:
        self._client.close()


class AsyncResponseStream(AsyncByteStream):
    def __init__(self, native: typing.Any) -> None:
        self._native = native

    async def __aiter__(self) -> typing.AsyncIterator[bytes]:
        try:
            while (
                chunk := await anyio.to_thread.run_sync(
                    self._native.read_chunk, abandon_on_cancel=True
                )
            ) is not None:
                yield chunk
        except BaseException:
            self._native.cancel()
            raise

    async def aclose(self) -> None:
        self._native.cancel()
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(self._native.close)


class AsyncHTTPTransport(AsyncBaseTransport):
    def __init__(
        self,
        verify: ssl.SSLContext | str | bool = True,
        cert: CertTypes | None = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        proxy: ProxyTypes | None = None,
        uds: str | None = None,
        local_address: str | None = None,
        retries: int = 0,
        socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
        *,
        privacy_options: typing.Mapping[str, typing.Any] | None = None,
    ) -> None:
        self._transport = HTTPTransport(
            verify,
            cert,
            trust_env,
            http1,
            http2,
            limits,
            proxy,
            uds,
            local_address,
            retries,
            socket_options,
            privacy_options=privacy_options,
        )

    async def handle_async_request(self, request: Request) -> Response:
        assert isinstance(request.stream, AsyncByteStream)
        stream = request.stream.__aiter__()

        async def next_chunk() -> bytes | None:
            try:
                return await stream.__anext__()
            except StopAsyncIteration:
                return None

        from .._native import NativeCancellation

        cancellation = NativeCancellation()
        options = _request_options(request)
        options["_cancel"] = cancellation
        failure: BaseException | None = None
        try:
            async with BlockingPortal() as portal:

                def chunks() -> typing.Iterator[bytes]:
                    while (chunk := portal.call(next_chunk)) is not None:
                        yield chunk

                try:
                    for attempt in range(self._transport._retries + 1):
                        if attempt > 1:
                            await anyio.sleep(0.5 * 2 ** (attempt - 2))
                        try:
                            native = await anyio.to_thread.run_sync(
                                self._transport._client.send,
                                request.method,
                                str(request.url),
                                request.headers.raw,
                                _request_body(request, chunks()),
                                options,
                                abandon_on_cancel=True,
                            )
                            await portal.stop(cancel_remaining=True)
                            break
                        except (ConnectError, ConnectTimeout):
                            if attempt == self._transport._retries:
                                raise
                except BaseException as exc:
                    cancellation.cancel()
                    failure = exc
                    with anyio.CancelScope(shield=True):
                        await portal.stop(cancel_remaining=True)
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                with anyio.CancelScope(shield=True):
                    await close()
        if failure is not None:
            raise failure
        return _response(native, AsyncResponseStream(native))

    async def aclose(self) -> None:
        await anyio.to_thread.run_sync(self._transport.close)
