import httpxp


def hello_world(request: httpxp.Request) -> httpxp.Response:
    return httpxp.Response(200, text="Hello, world")


def test_client_queryparams():
    client = httpxp.Client(params={"a": "b"})
    assert isinstance(client.params, httpxp.QueryParams)
    assert client.params["a"] == "b"


def test_client_queryparams_string():
    client = httpxp.Client(params="a=b")
    assert isinstance(client.params, httpxp.QueryParams)
    assert client.params["a"] == "b"

    client = httpxp.Client()
    client.params = "a=b"
    assert isinstance(client.params, httpxp.QueryParams)
    assert client.params["a"] == "b"


def test_client_queryparams_echo():
    url = "http://example.org/echo_queryparams"
    client_queryparams = "first=str"
    request_queryparams = {"second": "dict"}
    client = httpxp.Client(
        transport=httpxp.MockTransport(hello_world), params=client_queryparams
    )
    response = client.get(url, params=request_queryparams)

    assert response.status_code == 200
    assert response.url == "http://example.org/echo_queryparams?first=str&second=dict"
