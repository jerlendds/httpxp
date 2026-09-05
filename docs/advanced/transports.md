HTTPXP's `Client` also accepts a `transport` argument. This argument allows you
to provide a custom Transport object that will be used to perform the actual
sending of the requests.

## HTTP Transport

For some advanced configuration you might need to instantiate a transport
class directly, and pass it to the client instance. One example is the
`local_address` configuration which is only available via this low-level API.

```pycon
>>> import httpxp
>>> transport = httpxp.HTTPTransport(local_address="0.0.0.0")
>>> client = httpxp.Client(transport=transport)
```

Connection retries are also available via this interface. Requests will be retried the given number of times in case an `httpxp.ConnectError` or an `httpxp.ConnectTimeout` occurs, allowing smoother operation under flaky networks. If you need other forms of retry behaviors, such as handling read/write errors or reacting to `503 Service Unavailable`, consider general-purpose tools such as [tenacity](https://github.com/jd/tenacity).

```pycon
>>> import httpxp
>>> transport = httpxp.HTTPTransport(retries=1)
>>> client = httpxp.Client(transport=transport)
```

Similarly, instantiating a transport directly provides a `uds` option for
connecting via a Unix Domain Socket that is only available via this low-level API:

```pycon
>>> import httpxp
>>> # Connect to the Docker API via a Unix Socket.
>>> transport = httpxp.HTTPTransport(uds="/var/run/docker.sock")
>>> client = httpxp.Client(transport=transport)
>>> response = client.get("http://docker/info")
>>> response.json()
{"ID": "...", "Containers": 4, "Images": 74, ...}
```

## WSGI Transport

You can configure an `httpxp` client to call directly into a Python web application using the WSGI protocol.

This is particularly useful for two main use-cases:

* Using `httpxp` as a client inside test cases.
* Mocking out external services during tests or in dev or staging environments.

### Example

Here's an example of integrating against a Flask application:

```python
from flask import Flask
import httpxp


app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello World!"

transport = httpxp.WSGITransport(app=app)
with httpxp.Client(transport=transport, base_url="http://testserver") as client:
    r = client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello World!"
```

### Configuration

For some more complex cases you might need to customize the WSGI transport. This allows you to:

* Inspect 500 error responses rather than raise exceptions by setting `raise_app_exceptions=False`.
* Mount the WSGI application at a subpath by setting `script_name` (WSGI).
* Use a given client address for requests by setting `remote_addr` (WSGI).

For example:

```python
# Instantiate a client that makes WSGI requests with a client IP of "1.2.3.4".
transport = httpxp.WSGITransport(app=app, remote_addr="1.2.3.4")
with httpxp.Client(transport=transport, base_url="http://testserver") as client:
    ...
```

## ASGI Transport

You can configure an `httpxp` client to call directly into an async Python web application using the ASGI protocol.

This is particularly useful for two main use-cases:

* Using `httpxp` as a client inside test cases.
* Mocking out external services during tests or in dev or staging environments.

### Example

Let's take this Starlette application as an example:

```python
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route


async def hello(request):
    return HTMLResponse("Hello World!")


app = Starlette(routes=[Route("/", hello)])
```

We can make requests directly against the application, like so:

```python
transport = httpxp.ASGITransport(app=app)

async with httpxp.AsyncClient(transport=transport, base_url="http://testserver") as client:
    r = await client.get("/")
    assert r.status_code == 200
    assert r.text == "Hello World!"
```

### Configuration

For some more complex cases you might need to customise the ASGI transport. This allows you to:

* Inspect 500 error responses rather than raise exceptions by setting `raise_app_exceptions=False`.
* Mount the ASGI application at a subpath by setting `root_path`.
* Use a given client address for requests by setting `client`.

For example:

```python
# Instantiate a client that makes ASGI requests with a client IP of "1.2.3.4",
# on port 123.
transport = httpxp.ASGITransport(app=app, client=("1.2.3.4", 123))
async with httpxp.AsyncClient(transport=transport, base_url="http://testserver") as client:
    ...
```

See [the ASGI documentation](https://asgi.readthedocs.io/en/latest/specs/www.html#connection-scope) for more details on the `client` and `root_path` keys.

### ASGI startup and shutdown

It is not in the scope of HTTPXP to trigger ASGI lifespan events of your app.

However it is suggested to use `LifespanManager` from [asgi-lifespan](https://github.com/florimondmanca/asgi-lifespan#usage) in pair with `AsyncClient`.

## Custom transports

A transport instance must implement the low-level Transport API which deals
with sending a single request, and returning a response. You should either
subclass `httpxp.BaseTransport` to implement a transport to use with `Client`,
or subclass `httpxp.AsyncBaseTransport` to implement a transport to
use with `AsyncClient`.

At the layer of the transport API we're using the familiar `Request` and
`Response` models.

See the `handle_request` and `handle_async_request` docstrings for more details
on the specifics of the Transport API.

A complete example of a custom transport implementation would be:

```python
import json
import httpxp

class HelloWorldTransport(httpxp.BaseTransport):
    """
    A mock transport that always returns a JSON "Hello, world!" response.
    """

    def handle_request(self, request):
        return httpxp.Response(200, json={"text": "Hello, world!"})
```

Or this example, which uses a custom transport and `httpxp.Mounts` to always redirect `http://` requests.

```python
class HTTPSRedirect(httpxp.BaseTransport):
    """
    A transport that always redirects to HTTPS.
    """
    def handle_request(self, request):
        url = request.url.copy_with(scheme="https")
        return httpxp.Response(303, headers={"Location": str(url)})

# A client where any `http` requests are always redirected to `https`
transport = httpxp.Mounts({
    'http://': HTTPSRedirect()
    'https://': httpxp.HTTPTransport()
})
client = httpxp.Client(transport=transport)
```

A useful pattern here is custom transport classes that wrap the default HTTP implementation. For example...

```python
class DebuggingTransport(httpxp.BaseTransport):
    def __init__(self, **kwargs):
        self._wrapper = httpxp.HTTPTransport(**kwargs)

    def handle_request(self, request):
        print(f">>> {request}")
        response = self._wrapper.handle_request(request)
        print(f"<<< {response}")
        return response

    def close(self):
        self._wrapper.close()

transport = DebuggingTransport()
client = httpxp.Client(transport=transport)
```

Here's another case, where we're using a round-robin across a number of different proxies...

```python
class ProxyRoundRobin(httpxp.BaseTransport):
    def __init__(self, proxies, **kwargs):
        self._transports = [
            httpxp.HTTPTransport(proxy=proxy, **kwargs)
            for proxy in proxies
        ]
        self._idx = 0

    def handle_request(self, request):
        transport = self._transports[self._idx]
        self._idx = (self._idx + 1) % len(self._transports)
        return transport.handle_request(request)

    def close(self):
        for transport in self._transports:
            transport.close()

proxies = [
    httpxp.Proxy("http://127.0.0.1:8081"),
    httpxp.Proxy("http://127.0.0.1:8082"),
    httpxp.Proxy("http://127.0.0.1:8083"),
]
transport = ProxyRoundRobin(proxies=proxies)
client = httpxp.Client(transport=transport)
```

## Mock transports

During testing it can often be useful to be able to mock out a transport,
and return pre-determined responses, rather than making actual network requests.

The `httpxp.MockTransport` class accepts a handler function, which can be used
to map requests onto pre-determined responses:

```python
def handler(request):
    return httpxp.Response(200, json={"text": "Hello, world!"})


# Switch to a mock transport, if the TESTING environment variable is set.
if os.environ.get('TESTING', '').upper() == "TRUE":
    transport = httpxp.MockTransport(handler)
else:
    transport = httpxp.HTTPTransport()

client = httpxp.Client(transport=transport)
```

For more advanced use-cases you might want to take a look at either [the third-party
mocking library, RESPX](https://lundberg.github.io/respx/), or the [pytest-httpx library](https://github.com/Colin-b/pytest_httpx).

## Mounting transports

You can also mount transports against given schemes or domains, to control
which transport an outgoing request should be routed via, with [the same style
used for specifying proxy routing](#routing).

```python
import httpxp

class HTTPSRedirectTransport(httpxp.BaseTransport):
    """
    A transport that always redirects to HTTPS.
    """

    def handle_request(self, method, url, headers, stream, extensions):
        scheme, host, port, path = url
        if port is None:
            location = b"https://%s%s" % (host, path)
        else:
            location = b"https://%s:%d%s" % (host, port, path)
        stream = httpxp.ByteStream(b"")
        headers = [(b"location", location)]
        extensions = {}
        return 303, headers, stream, extensions


# A client where any `http` requests are always redirected to `https`
mounts = {'http://': HTTPSRedirectTransport()}
client = httpxp.Client(mounts=mounts)
```

A couple of other sketches of how you might take advantage of mounted transports...

Disabling HTTP/2 on a single given domain...

```python
mounts = {
    "all://": httpxp.HTTPTransport(http2=True),
    "all://*example.org": httpxp.HTTPTransport()
}
client = httpxp.Client(mounts=mounts)
```

Mocking requests to a given domain:

```python
# All requests to "example.org" should be mocked out.
# Other requests occur as usual.
def handler(request):
    return httpxp.Response(200, json={"text": "Hello, World!"})

mounts = {"all://example.org": httpxp.MockTransport(handler)}
client = httpxp.Client(mounts=mounts)
```

Adding support for custom schemes:

```python
# Support URLs like "file:///Users/sylvia_green/websites/new_client/index.html"
mounts = {"file://": FileSystemTransport()}
client = httpxp.Client(mounts=mounts)
```

### Routing

HTTPXP provides a powerful mechanism for routing requests, allowing you to write complex rules that specify which transport should be used for each request.

The `mounts` dictionary maps URL patterns to HTTP transports. HTTPXP matches requested URLs against URL patterns to decide which transport should be used, if any. Matching is done from most specific URL patterns (e.g. `https://<domain>:<port>`) to least specific ones (e.g. `https://`).

HTTPXP supports routing requests based on **scheme**, **domain**, **port**, or a combination of these.

### Wildcard routing

Route everything through a transport...

```python
mounts = {
    "all://": httpxp.HTTPTransport(proxy="http://localhost:8030"),
}
```

### Scheme routing

Route HTTP requests through one transport, and HTTPS requests through another...

```python
mounts = {
    "http://": httpxp.HTTPTransport(proxy="http://localhost:8030"),
    "https://": httpxp.HTTPTransport(proxy="http://localhost:8031"),
}
```

### Domain routing

Proxy all requests on domain "example.com", let other requests pass through...

```python
mounts = {
    "all://example.com": httpxp.HTTPTransport(proxy="http://localhost:8030"),
}
```

Proxy HTTP requests on domain "example.com", let HTTPS and other requests pass through...

```python
mounts = {
    "http://example.com": httpxp.HTTPTransport(proxy="http://localhost:8030"),
}
```

Proxy all requests to "example.com" and its subdomains, let other requests pass through...

```python
mounts = {
    "all://*example.com": httpxp.HTTPTransport(proxy="http://localhost:8030"),
}
```

Proxy all requests to strict subdomains of "example.com", let "example.com" and other requests pass through...

```python
mounts = {
    "all://*.example.com": httpxp.HTTPTransport(proxy="http://localhost:8030"),
}
```

### Port routing

Proxy HTTPS requests on port 1234 to "example.com"...

```python
mounts = {
    "https://example.com:1234": httpxp.HTTPTransport(proxy="http://localhost:8030"),
}
```

Proxy all requests on port 1234...

```python
mounts = {
    "all://*:1234": httpxp.HTTPTransport(proxy="http://localhost:8030"),
}
```

### No-proxy support

It is also possible to define requests that _shouldn't_ be routed through the transport.

To do so, pass `None` as the proxy URL. For example...

```python
mounts = {
    # Route requests through a proxy by default...
    "all://": httpxp.HTTPTransport(proxy="http://localhost:8031"),
    # Except those for "example.com".
    "all://example.com": None,
}
```

### Complex configuration example

You can combine the routing features outlined above to build complex proxy routing configurations. For example...

```python
mounts = {
    # Route all traffic through a proxy by default...
    "all://": httpxp.HTTPTransport(proxy="http://localhost:8030"),
    # But don't use proxies for HTTPS requests to "domain.io"...
    "https://domain.io": None,
    # And use another proxy for requests to "example.com" and its subdomains...
    "all://*example.com": httpxp.HTTPTransport(proxy="http://localhost:8031"),
    # And yet another proxy if HTTP is used,
    # and the "internal" subdomain on port 5550 is requested...
    "http://internal.example.com:5550": httpxp.HTTPTransport(proxy="http://localhost:8032"),
}
```

### Environment variables

There are also environment variables that can be used to control the dictionary of the client mounts. 
They can be used to configure HTTP proxying for clients.

See documentation on [`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`](../environment_variables.md#http_proxy-https_proxy-all_proxy)
and [`NO_PROXY`](../environment_variables.md#no_proxy) for more information.
