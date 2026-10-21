from __future__ import annotations

"""WireGuard/Tailscale-only opaque TCP bridge to an existing read-only Gateway.

This module does not authenticate to IBKR or understand/alter broker protocol.
Source and destination are bound by explicit CLI constants, never by clients.
The active IB Gateway MUST have READ_ONLY_API=yes.
"""

import argparse
import asyncio
import ipaddress
import os
from typing import Any


def validate_tailnet_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("gateway_pool_numeric_tailnet_ip_required") from exc
    if ip.version != 4 or ip not in ipaddress.ip_network("100.64.0.0/10"):
        raise ValueError("gateway_pool_tailnet_ipv4_required")
    return str(ip)


async def bridge(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    *,
    upstream_host: str = "127.0.0.1",
    upstream_port: int = 4001,
) -> None:
    upstream_writer: asyncio.StreamWriter | None = None
    tasks: list[asyncio.Task[Any]] = []
    try:
        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(upstream_host, upstream_port), timeout=8,
        )

        async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                while buf := await reader.read(32768):
                    writer.write(buf)
                    await writer.drain()
            finally:
                if writer.can_write_eof():
                    writer.write_eof()

        tasks = [
            asyncio.create_task(pipe(client_reader, upstream_writer)),
            asyncio.create_task(pipe(upstream_reader, client_writer)),
        ]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (OSError, ConnectionError, asyncio.TimeoutError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for writer in (client_writer, upstream_writer):
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, ConnectionError):
                    pass


async def serve(listen_host: str, *, listen_port: int = 4001) -> None:
    ip = validate_tailnet_ip(listen_host)
    if not 1 <= listen_port <= 65535:
        raise ValueError("gateway_pool_invalid_port")
    server = await asyncio.start_server(
        lambda r, w: bridge(r, w), ip, listen_port,
        limit=65536,
    )
    print("MMIBKR_SPLIT_GATEWAY_PRIVATE_RELAY_ACTIVE=1", flush=True)
    print("MMIBKR_SPLIT_GATEWAY_RELAY_MUTATION_AUTHORITY=NONE", flush=True)
    async with server:
        await server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-ip", required=True)
    parser.add_argument("--port", type=int, default=4001)
    args = parser.parse_args()
    # No listeners are ever opened for public, loopback, or arbitrary DNS IPs.
    asyncio.run(serve(args.private_ip, listen_port=args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
