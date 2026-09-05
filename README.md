<p align="center">
  <a href="https://github.com/jerlendds/httpxp/blob/master/docs/index.md"><img width="350" height="208" src="https://raw.githubusercontent.com/jerlendds/httpxp/master/docs/img/logo.svg" alt='HTTPXP'></a>
</p>

<p align="center"><strong>HTTPXP</strong> <em>- A next-generation HTTP client for Python.</em></p>

<p align="center">
<a href="https://github.com/jerlendds/httpxp/actions">
    <img src="https://github.com/jerlendds/httpxp/workflows/Test%20Suite/badge.svg" alt="Test Suite">
</a>
<a href="https://pypi.org/project/httpxp/">
    <img src="https://badge.fury.io/py/httpxp.svg" alt="Package version">
</a>
</p>

HTTPXP is a fully featured HTTP client library for Python 3. It includes **an integrated command line client**, has support for both **HTTP/1.1 and HTTP/2**, and provides both **sync and async APIs**.

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
$ pip install 'httpxp[cli]'  # The command line client is an optional dependency.
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

* A broadly [requests-compatible API](https://github.com/jerlendds/httpxp/blob/master/docs/compatibility.md).
* An integrated command-line client.
* HTTP/1.1 [and HTTP/2 support](https://github.com/jerlendds/httpxp/blob/master/docs/http2.md).
* Standard synchronous interface, but with [async support if you need it](https://github.com/jerlendds/httpxp/blob/master/docs/async.md).
* Ability to make requests directly to [WSGI applications](https://github.com/jerlendds/httpxp/blob/master/docs/advanced/transports.md#wsgi-transport) or [ASGI applications](https://github.com/jerlendds/httpxp/blob/master/docs/advanced/transports.md#asgi-transport).
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

HTTPXP requires Python 3.9+.

## Documentation

Project documentation is available at [https://github.com/jerlendds/httpxp/blob/master/docs/index.md](https://github.com/jerlendds/httpxp/blob/master/docs/index.md).

For a run-through of all the basics, head over to the [QuickStart](https://github.com/jerlendds/httpxp/blob/master/docs/quickstart.md).

For more advanced topics, see the [Advanced Usage](https://github.com/jerlendds/httpxp/blob/master/docs/advanced/clients.md) section, the [async support](https://github.com/jerlendds/httpxp/blob/master/docs/async.md) section, or the [HTTP/2](https://github.com/jerlendds/httpxp/blob/master/docs/http2.md) section.

The [Developer Interface](https://github.com/jerlendds/httpxp/blob/master/docs/api.md) provides a comprehensive API reference.

For the upstream ecosystem and compatibility notes, see [Third Party Packages](https://github.com/jerlendds/httpxp/blob/master/docs/third_party_packages.md).

## Contribute

If you want to contribute with HTTPXP check out the [Contributing Guide](https://github.com/jerlendds/httpxp/blob/master/docs/contributing.md) to learn how to start.

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

---

<p align="center"><i>HTTPXP is <a href="https://github.com/jerlendds/httpxp/blob/master/LICENSE.md">BSD licensed</a> code.<br/>Designed & crafted with care.</i><br/>&mdash; 🦋 &mdash;</p>

## Native privacy settings

```python
with httpxp.Client(privacy_options={"emulation": "Chrome149"}) as client:
    response = client.get(
        "https://example.com",
        extensions={"private": {"group": "account-one"}},
    )
```

See the [privacy guide](docs/advanced/wreq.md),
[complete implemented option reference](docs/advanced/privacy-options.md), and
[API coverage audit](docs/advanced/wreq-coverage.md). The migration is still in
progress; the audit explicitly lists unsupported callbacks/runtime features,
WebSocket limitations, and compatibility gaps.

Source installs build a PyO3 extension with Maturin and require Rust 1.98 or
newer plus the native BoringSSL build tools (C/C++ compiler, CMake, Perl, and
Clang/libclang). Prebuilt compatible wheels do not require a local Rust build.
For development with a suitable installed nightly toolchain:

```sh
python -m venv .venv
.venv/bin/pip install maturin
RUSTUP_TOOLCHAIN=nightly .venv/bin/maturin develop
```

Run the supplied examples from the source checkout after installation with
`python -m examples.private_proxy --help` or
`python -m examples.private_websocket --help`.
