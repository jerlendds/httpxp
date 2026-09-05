# Exceptions

This page lists exceptions that may be raised when using HTTPXP.

For an overview of how to work with HTTPXP exceptions, see [Exceptions (Quickstart)](quickstart.md#exceptions).

## The exception hierarchy

* HTTPError
    * RequestError
        * TransportError
            * TimeoutException
                * ConnectTimeout
                * ReadTimeout
                * WriteTimeout
                * PoolTimeout
            * NetworkError
                * ConnectError
                * ReadError
                * WriteError
                * CloseError
            * ProtocolError
                * LocalProtocolError
                * RemoteProtocolError
            * ProxyError
            * UnsupportedProtocol
        * DecodingError
        * TooManyRedirects
    * HTTPStatusError
* InvalidURL
* CookieConflict
* StreamError
    * StreamConsumed
    * ResponseNotRead
    * RequestNotRead
    * StreamClosed

---

## Exception classes

::: httpxp.HTTPError
    :docstring:

::: httpxp.RequestError
    :docstring:

::: httpxp.TransportError
    :docstring:

::: httpxp.TimeoutException
    :docstring:

::: httpxp.ConnectTimeout
    :docstring:

::: httpxp.ReadTimeout
    :docstring:

::: httpxp.WriteTimeout
    :docstring:

::: httpxp.PoolTimeout
    :docstring:

::: httpxp.NetworkError
    :docstring:

::: httpxp.ConnectError
    :docstring:

::: httpxp.ReadError
    :docstring:

::: httpxp.WriteError
    :docstring:

::: httpxp.CloseError
    :docstring:

::: httpxp.ProtocolError
    :docstring:

::: httpxp.LocalProtocolError
    :docstring:

::: httpxp.RemoteProtocolError
    :docstring:

::: httpxp.ProxyError
    :docstring:

::: httpxp.UnsupportedProtocol
    :docstring:

::: httpxp.DecodingError
    :docstring:

::: httpxp.TooManyRedirects
    :docstring:

::: httpxp.HTTPStatusError
    :docstring:

::: httpxp.InvalidURL
    :docstring:

::: httpxp.CookieConflict
    :docstring:

::: httpxp.StreamError
    :docstring:

::: httpxp.StreamConsumed
    :docstring:

::: httpxp.StreamClosed
    :docstring:

::: httpxp.ResponseNotRead
    :docstring:

::: httpxp.RequestNotRead
    :docstring:
