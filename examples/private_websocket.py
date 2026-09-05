"""The supplied wreq WebSocket examples, using the httpxp Python API.

Run against a WebSocket echo service:
    python examples/private_websocket.py ws://localhost:3000/ws
    python examples/private_websocket.py wss://localhost:3000/ws --http2 --ca ca.pem
    python examples/private_websocket.py ws://localhost:3000/ws --async-client
"""

from __future__ import annotations

import argparse
from pathlib import Path

import anyio

import httpxp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--http2", action="store_true")
    parser.add_argument("--ca", type=Path)
    parser.add_argument("--async-client", action="store_true")
    args = parser.parse_args()
    options = {"tls_cert_store_pem": args.ca.read_bytes()} if args.ca else {}
    version = "2" if args.http2 else "1.1"

    async def run_async() -> None:
        async with httpxp.AsyncClient(
            http1=not args.http2, http2=args.http2, privacy_options=options
        ) as client:
            async with await client.websocket(
                args.url, version=version, read_buffer_size=1024 * 1024
            ) as socket:
                print(socket.response.http_version, socket.protocol)

                async def send() -> None:
                    for i in range(1, 11):
                        await socket.send_text(f"Hello, World! #{i}")

                async with anyio.create_task_group() as group:
                    group.start_soon(send)
                    received = 0
                    async for message in socket:
                        if message.type == "text":
                            print(message.data)
                            received += 1
                            if received == 10:
                                break

    if args.async_client:
        anyio.run(run_async)
    else:
        with httpxp.Client(
            http1=not args.http2, http2=args.http2, privacy_options=options
        ) as client:
            with client.websocket(
                args.url, version=version, read_buffer_size=1024 * 1024
            ) as socket:
                print(socket.response.http_version, socket.protocol)
                for i in range(1, 11):
                    socket.send_text(f"Hello, World! #{i}")
                    message = socket.receive()
                    print(message.data if message else "closed")


if __name__ == "__main__":
    main()
