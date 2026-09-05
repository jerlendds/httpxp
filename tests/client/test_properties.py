import httpxp


def test_client_base_url():
    client = httpxp.Client()
    client.base_url = "https://www.example.org/"
    assert isinstance(client.base_url, httpxp.URL)
    assert client.base_url == "https://www.example.org/"


def test_client_base_url_without_trailing_slash():
    client = httpxp.Client()
    client.base_url = "https://www.example.org/path"
    assert isinstance(client.base_url, httpxp.URL)
    assert client.base_url == "https://www.example.org/path/"


def test_client_base_url_with_trailing_slash():
    client = httpxp.Client()
    client.base_url = "https://www.example.org/path/"
    assert isinstance(client.base_url, httpxp.URL)
    assert client.base_url == "https://www.example.org/path/"


def test_client_headers():
    client = httpxp.Client()
    client.headers = {"a": "b"}
    assert isinstance(client.headers, httpxp.Headers)
    assert client.headers["A"] == "b"


def test_client_cookies():
    client = httpxp.Client()
    client.cookies = {"a": "b"}
    assert isinstance(client.cookies, httpxp.Cookies)
    mycookies = list(client.cookies.jar)
    assert len(mycookies) == 1
    assert mycookies[0].name == "a" and mycookies[0].value == "b"


def test_client_timeout():
    expected_timeout = 12.0
    client = httpxp.Client()

    client.timeout = expected_timeout

    assert isinstance(client.timeout, httpxp.Timeout)
    assert client.timeout.connect == expected_timeout
    assert client.timeout.read == expected_timeout
    assert client.timeout.write == expected_timeout
    assert client.timeout.pool == expected_timeout


def test_client_event_hooks():
    def on_request(request):
        pass  # pragma: no cover

    client = httpxp.Client()
    client.event_hooks = {"request": [on_request]}
    assert client.event_hooks == {"request": [on_request], "response": []}


def test_client_trust_env():
    client = httpxp.Client()
    assert client.trust_env

    client = httpxp.Client(trust_env=False)
    assert not client.trust_env
