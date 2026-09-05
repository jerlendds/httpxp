"""Request through HTTP, HTTPS, SOCKS5/SOCKS5H, or Unix socket proxies.

    python examples/private_proxy.py https://api.ip.sb/ip socks5h://localhost:6153
    python examples/private_proxy.py https://check.torproject.org socks5h://localhost:9050
    python examples/private_proxy.py http://localhost/info /var/run/docker.sock --unix
    python examples/private_proxy.py https://example.com http://localhost:8080

Add --request-proxy to configure the proxy on the request instead of the client.
"""

from __future__ import annotations

import argparse
from typing import Any

import httpxp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("proxy")
    parser.add_argument("--unix", action="store_true")
    parser.add_argument("--request-proxy", action="store_true")
    parser.add_argument("--no-proxy", help="Comma-separated proxy exclusions")
    args = parser.parse_args()
    proxy: dict[str, Any] = {
        "url": args.proxy,
        "scheme": "unix" if args.unix else "all",
    }
    if args.no_proxy:
        proxy["no_proxy"] = args.no_proxy
    with httpxp.Client(
        trust_env=False,
        timeout=10,
        privacy_options={} if args.request_proxy else {"proxy": proxy},
    ) as client:
        response = client.get(
            args.url,
            extensions={"private": {"proxy": proxy}} if args.request_proxy else {},
        )
        print("Status:", response.status_code)
        print(response.text)


if __name__ == "__main__":
    main()
