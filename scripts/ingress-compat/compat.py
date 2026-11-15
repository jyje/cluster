#!/usr/bin/env python3
"""Compare ingress-nginx and Higress behavior for long-lived connections.

Part of the ingress-nginx to Higress evaluation (tracking issue #314). It runs
the same requests against test Ingresses exposed through both controllers, and
reports what each one does. Nothing here changes the cluster: it only starts
`kubectl port-forward` and sends requests to hosts that do not resolve.

The test objects live in clusters/r4spi/apps/higress.yaml (the `c-*` Ingresses
and the httpbin and whoami backends). Standard library only.

Usage:
  scripts/ingress-compat/compat.py --context microk8s
  scripts/ingress-compat/compat.py --context microk8s --hold 75 --json out.json
"""

import argparse
import base64
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time

# Variants are (controller, label, host). The first column of the report.
VARIANTS = [
    ("nginx", "nginx, no annotation", "nginx-default.compat.invalid"),
    ("nginx", "nginx, proxy-*-timeout 3600", "nginx-3600.compat.invalid"),
    ("higress", "higress, no annotation", "higress-default.compat.invalid"),
    ("higress", "higress, nginx names (3600)", "higress-nginx-names.compat.invalid"),
    ("higress", "higress, higress.io/timeout 3600", "higress-3600.compat.invalid"),
]

# Local ports are picked at run time, so a port that something else already
# listens on is never reused (a clash would send the tests to the wrong server).
PORTS = {}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def port_forward(context, controller):
    """Start a port-forward for the controller and return the process."""
    PORTS[controller] = free_port()
    if controller == "higress":
        # Forward to the pod, as for ingress-nginx. A Service forward picks a
        # pod once and was seen dropping long connections.
        pod = subprocess.check_output(
            ["kubectl", "--context", context, "-n", "higress-system", "get", "pods",
             "-l", "app=higress-gateway",
             "-o", "jsonpath={.items[0].metadata.name}"], text=True).strip()
        target = ["-n", "higress-system", f"pod/{pod}", f"{PORTS[controller]}:80"]
    else:
        pod = subprocess.check_output(
            ["kubectl", "--context", context, "-n", "kube-system", "get", "pods",
             "-l", "app.kubernetes.io/name=ingress-nginx",
             "-o", "jsonpath={.items[0].metadata.name}"], text=True).strip()
        target = ["-n", "kube-system", f"pod/{pod}", f"{PORTS[controller]}:80"]
    log = open(f"/tmp/compat-port-forward-{controller}.log", "w")
    proc = subprocess.Popen(["kubectl", "--context", context, "port-forward", *target],
                            stdout=log, stderr=log)
    for _ in range(60):
        if proc.poll() is not None:
            raise SystemExit(f"port-forward for {controller} exited early")
        try:
            socket.create_connection(("127.0.0.1", PORTS[controller]), timeout=1).close()
            return proc
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit(f"port-forward for {controller} did not start")


def result(ok, detail, started):
    return {"ok": ok, "detail": detail, "seconds": round(time.time() - started, 1)}


def test_delay(port, host, hold):
    """One response that arrives after `hold` seconds with no bytes before it."""
    started = time.time()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=hold + 40)
        conn.request("GET", f"/delay/{hold}", headers={"Host": host})
        resp = conn.getresponse()
        resp.read()
        return result(resp.status == 200, f"HTTP {resp.status}", started)
    except Exception as exc:  # noqa: BLE001 - report any failure as the result
        return result(False, f"{type(exc).__name__}", started)


def test_drip(port, host, hold):
    """A response streamed one byte per second, like SSE: bytes keep flowing."""
    started = time.time()
    total = hold + 15
    got = 0
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        conn.request("GET", f"/drip?duration={total}&numbytes={total}&code=200",
                     headers={"Host": host})
        resp = conn.getresponse()
        if resp.status != 200:
            return result(False, f"HTTP {resp.status}", started)
        while True:
            chunk = resp.read(64)
            if not chunk:
                break
            got += len(chunk)
        return result(got == total, f"{got}/{total} bytes", started)
    except Exception as exc:  # noqa: BLE001
        return result(False, f"{type(exc).__name__} after {got}/{total} bytes", started)


def ws_send(sock, text):
    payload = text.encode()
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes([0x81, 0x80 | len(payload)]) + mask + masked)


def ws_recv(sock):
    header = sock.recv(2)
    if len(header) < 2:
        raise ConnectionError("connection closed")
    opcode, length = header[0] & 0x0F, header[1] & 0x7F
    data = b""
    while len(data) < length:
        part = sock.recv(length - len(data))
        if not part:
            raise ConnectionError("connection closed")
        data += part
    if opcode == 0x8:
        raise ConnectionError("close frame")
    return data.decode(errors="replace")


def test_websocket(port, host, hold):
    """A WebSocket that is idle for `hold` seconds, then used again."""
    started = time.time()
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=hold + 40)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET /echo HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                      f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += sock.recv(1024)
        status = head.split(b" ", 2)[1].decode()
        if status != "101":
            return result(False, f"handshake HTTP {status}", started)
        ws_send(sock, "before")
        ws_recv(sock)  # whoami echoes the first message back
        time.sleep(hold)
        ws_send(sock, "after")
        reply = ws_recv(sock)
        return result("after" in reply, f"idle {hold}s, echo ok", started)
    except Exception as exc:  # noqa: BLE001
        return result(False, f"{type(exc).__name__}: {exc}", started)


TESTS = [
    ("response delayed", test_delay),
    ("streamed 1 byte/s", test_drip),
    ("idle WebSocket", test_websocket),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--context", default="microk8s", help="kubectl context")
    parser.add_argument("--hold", type=int, default=75,
                        help="seconds a request waits (must be above the 60s nginx default)")
    parser.add_argument("--json", help="also write the raw results to this file")
    args = parser.parse_args()

    forwards = {c: port_forward(args.context, c) for c in {v[0] for v in VARIANTS}}
    results, lock, threads = {}, threading.Lock(), []

    def run(variant, name, func):
        controller, label, host = variant
        outcome = func(PORTS[controller], host, args.hold)
        with lock:
            results[(label, name)] = outcome

    try:
        for variant in VARIANTS:
            for name, func in TESTS:
                thread = threading.Thread(target=run, args=(variant, name, func))
                thread.start()
                threads.append(thread)
        for thread in threads:
            thread.join()
    finally:
        for proc in forwards.values():
            proc.terminate()

    names = [name for name, _ in TESTS]
    print(f"\nHold time: {args.hold}s (ingress-nginx default read timeout is 60s)\n")
    print("| Ingress | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for _, label, _ in VARIANTS:
        cells = []
        for name in names:
            r = results[(label, name)]
            cells.append(f"{'PASS' if r['ok'] else 'FAIL'} ({r['detail']}, {r['seconds']}s)")
        print(f"| {label} | " + " | ".join(cells) + " |")
    if args.json:
        with open(args.json, "w") as handle:
            json.dump({f"{k[0]} / {k[1]}": v for k, v in results.items()}, handle, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
