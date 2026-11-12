#!/usr/bin/env python3
"""Emit synthetic NetFlow v5 records to a local collector; no network traffic is captured."""
from __future__ import annotations

import argparse
import socket
import struct
import time


def netflow_v5_packet(sequence: int, now: int | None = None) -> bytes:
    """Build one documentation-only TCP flow record (60,000 bytes / 120 packets)."""
    if sequence < 0 or sequence > 0xFFFFFFFF:
        raise ValueError("NetFlow v5 sequence numbers must fit in an unsigned 32-bit field")
    now = int(time.time()) if now is None else now
    header = struct.pack(
        "!HHIIIIBBH",
        5, 1, 2000, now, 0, sequence, 0, 0, 0,
    )
    record = struct.pack(
        "!IIIHHIIIIHHBBBBHHBBH",
        int.from_bytes(socket.inet_aton("192.0.2.10"), "big"),
        int.from_bytes(socket.inet_aton("198.51.100.20"), "big"),
        0, 1, 2, 120, 60_000, 1000, 2000, 12345, 443,
        0, 27, 6, 0, 0, 0, 24, 24, 0,
    )
    return header + record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2056)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--rate", type=float, default=1.0, help="datagrams per second")
    parser.add_argument(
        "--sequence-start",
        type=int,
        default=1,
        help="first unique sequence number; use per-run ranges to survive log rotation",
    )
    args = parser.parse_args()
    if args.count < 1 or args.rate <= 0:
        parser.error("--count must be positive and --rate must be greater than zero")
    if args.sequence_start < 0:
        parser.error("--sequence-start must be non-negative")
    if args.sequence_start + args.count > 0xFFFFFFFF:
        parser.error("--sequence-start plus --count must remain in unsigned 32-bit range")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for offset in range(args.count):
            sock.sendto(
                netflow_v5_packet(args.sequence_start + offset),
                (args.host, args.port),
            )
            if offset + 1 < args.count:
                time.sleep(1.0 / args.rate)
    finally:
        sock.close()
    print(f"sent {args.count} synthetic NetFlow v5 datagram(s) to {args.host}:{args.port}/udp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
