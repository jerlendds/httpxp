<p align="center" style="margin: 0 0 10px">
  <img width="350" height="208" src="https://raw.githubusercontent.com/jerlendds/httpxp/master/docs/img/butterfly.png" alt='HTTPXP'>
</p>

<h1 align="center" style="font-size: 3rem; margin: -15px 0">
HTTPXP
</h1>

---

<div align="center">
<p>
<a href="https://github.com/jerlendds/httpxp/actions">
    <img src="https://github.com/jerlendds/httpxp/workflows/Test%20Suite/badge.svg" alt="Test Suite">
</a>
<a href="https://pypi.org/project/httpxp/">
    <img src="https://badge.fury.io/py/httpxp.svg" alt="Package version">
</a>
</p>

<em>A next-generation HTTP client for Python.</em>
</div>

HTTPXP is a fully featured HTTP client for Python 3, which provides sync and async APIs, and support for both HTTP/1.1 and HTTP/2.

---

Install HTTPXP using pip:

```shell
$ pip install httpxp
```

Now, let's get started:

```pycon
>>> import httpxp
>>> r = httpxp.get('https://www.example.org/')
>>> r
<Response [200 OK]>
>>> r.status_code
200
>>> r.headers['content-type']
'text/html; charset=UTF-8'
>>> r.text
'<!doctype html>\n<html>\n<head>\n<title>Example Domain</title>...'
```

Or, using the command-line client.

```shell
# The command line client is an optional dependency.
$ pip install 'httpxp[cli]'
```

Which now allows us to use HTTPXP directly from the command-line...

```shell
$ httpxp --help
```

Sending a request...

```shell
$ httpxp http://httpbin.org/json
```

## Features

HTTPXP builds on the well-established usability of `requests`, and gives you:

* A broadly [requests-compatible API](compatibility.md).
* Standard synchronous interface, but with [async support if you need it](async.md).
* HTTP/1.1 [and HTTP/2 support](http2.md).
* Ability to make requests directly to [WSGI applications](advanced/transports.md#wsgi-transport) or [ASGI applications](advanced/transports.md#asgi-transport).
* Strict timeouts everywhere.
* Fully type annotated.
* 100% test coverage.

Plus all the standard features of `requests`...

* International Domains and URLs
* Keep-Alive & Connection Pooling
* Sessions with Cookie Persistence
* Browser-style SSL Verification
* Basic/Digest Authentication
* Elegant Key/Value Cookies
* Automatic Decompression
* Automatic Content Decoding
* Unicode Response Bodies
* Multipart File Uploads
* HTTP(S) Proxy Support
* Connection Timeouts
* Streaming Downloads
* .netrc Support
* Chunked Requests

## Documentation

For a run-through of all the basics, head over to the [QuickStart](quickstart.md).

For more advanced topics, see the **Advanced** section,
the [async support](async.md) section, or the [HTTP/2](http2.md) section.

The [Developer Interface](api.md) provides a comprehensive API reference.

For the upstream ecosystem and compatibility notes, see [Third Party Packages](third_party_packages.md).

## Dependencies

The HTTPXP project relies on these excellent libraries:

* Rust `wreq` and PyO3 - Native HTTP/1, HTTP/2, TLS, SOCKS, and WebSocket transport.
* `certifi` - SSL certificates.
* `idna` - Internationalized domain name support.
* `anyio` - Async integration for asyncio and Trio.

As well as these optional installs:

* `h2` - Retained in the `httpxp[http2]` compatibility extra; native HTTP/2 does not require it.
* `socksio` - Retained in the `httpxp[socks]` compatibility extra; native SOCKS does not require it.
* `rich` - Rich terminal support. *(Optional, with `httpxp[cli]`)*
* `click` - Command line client support. *(Optional, with `httpxp[cli]`)*
* `brotli` or `brotlicffi` - Decoding for "brotli" compressed responses. *(Optional, with `httpxp[brotli]`)*
* `zstandard` - Decoding for "zstd" compressed responses. *(Optional, with `httpxp[zstd]`)*

A huge amount of credit is due to `requests` for the API layout that
much of this work follows, as well as to `urllib3` for plenty of design
inspiration around the lower-level networking details.

## Installation

Install with pip:

```shell
$ pip install httpxp
```

The native transport includes HTTP/2 and SOCKS. The following HTTP/2
compatibility extra remains available, but is not required for native HTTP/2:

```shell
$ pip install httpxp[http2]
```

To include the optional brotli and zstandard decoders support, use:

```shell
$ pip install httpxp[brotli,zstd]
```

HTTPXP requires Python 3.9+

[sync-support]: https://github.com/encode/httpx/issues/572
