from __future__ import annotations

import typing

import pytest

import httpxp

if typing.TYPE_CHECKING:  # pragma: no cover
    from conftest import TestServer


def test_transport_exception_exports() -> None:
    """The native migration preserves the public transport exception names."""
    names = {
        "TimeoutException",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "NetworkError",
        "ConnectError",
        "ReadError",
        "WriteError",
        "CloseError",
        "ProxyError",
        "UnsupportedProtocol",
        "ProtocolError",
        "LocalProtocolError",
        "RemoteProtocolError",
    }
    for name in names:
        assert name in httpxp.__all__
        assert issubclass(getattr(httpxp, name), httpxp.TransportError)


def test_native_exception_mapping(server: TestServer) -> None:
    """
    Native wreq errors use the existing Python exception classes.
    """
    impossible_port = 123456
    with pytest.raises(httpxp.ConnectError):
        httpxp.get(server.url.copy_with(port=impossible_port))

    with pytest.raises(httpxp.ReadTimeout):
        httpxp.get(
            server.url.copy_with(path="/slow_response"),
            timeout=httpxp.Timeout(5, read=0.01),
        )


def test_request_attribute() -> None:
    # Exception without request attribute
    exc = httpxp.ReadTimeout("Read operation timed out")
    with pytest.raises(RuntimeError):
        exc.request  # noqa: B018

    # Exception with request attribute
    request = httpxp.Request("GET", "https://www.example.com")
    exc = httpxp.ReadTimeout("Read operation timed out", request=request)
    assert exc.request == request
