#!/usr/bin/env python3
"""Verify a fresh UDP echo round trip through the Gateway's advertised address."""

import argparse
import secrets
import socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", help="Gateway address reachable by this client")
    parser.add_argument("--port", type=int, default=34197)
    args = parser.parse_args()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.connect((args.address, args.port))
        for _ in range(3):
            payload = b"envoy-poc:" + secrets.token_hex(16).encode("ascii")
            sock.send(payload)
            if sock.recv(256) != payload:
                raise SystemExit("UDP echo did not return the original payload")
    print("PASS: three UDP echo round trips")


if __name__ == "__main__":
    main()
