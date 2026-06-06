#!/usr/bin/env python3
"""
LiteLLM rolling-update health monitor.

Watches pod readiness transitions, polls /health/readiness in real-time,
and optionally fires an inference request to verify end-to-end operation.

Usage:
  python3 scripts/validate-litellm.py
  python3 scripts/validate-litellm.py --api-key <MASTER_KEY>
  python3 scripts/validate-litellm.py --namespace ollama-system --local-port 14000
"""

import argparse
import json
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

# ── defaults ──────────────────────────────────────────────────────────────────
NAMESPACE     = "ollama-system"
SERVICE       = "litellm"
SERVICE_PORT  = 4000
LOCAL_PORT    = 14000
POLL_INTERVAL = 0.5   # seconds between health polls
POD_LABEL     = "app.kubernetes.io/name=litellm"

# ── ANSI colors ───────────────────────────────────────────────────────────────
C = {
    "green":  "\033[32m",
    "red":    "\033[31m",
    "yellow": "\033[33m",
    "cyan":   "\033[36m",
    "gray":   "\033[90m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}

stop_event = threading.Event()

# ── stats shared across threads ───────────────────────────────────────────────
stats = {
    "total":    0,
    "ok":       0,
    "fail":     0,
    "first_ok": None,   # timestamp of first successful health check
    "last_fail": None,
    "downtime_start": None,
    "total_downtime": 0.0,
}
stats_lock = threading.Lock()


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg: str, color: str = None) -> None:
    prefix = C.get(color, "") if color else ""
    reset  = C["reset"] if color else ""
    print(f"[{ts()}] {prefix}{msg}{reset}", flush=True)


# ── health poller ─────────────────────────────────────────────────────────────

def health_poller(local_port: int) -> None:
    prev = None        # "ok" | "fail" | "down"
    consecutive_ok = 0

    while not stop_event.is_set():
        status, label = _check_health(local_port)

        with stats_lock:
            stats["total"] += 1
            if status == "ok":
                stats["ok"] += 1
                consecutive_ok += 1
                if stats["first_ok"] is None:
                    stats["first_ok"] = time.time()
                if stats["downtime_start"] is not None:
                    stats["total_downtime"] += time.time() - stats["downtime_start"]
                    stats["downtime_start"] = None
            else:
                stats["fail"] += 1
                consecutive_ok = 0
                stats["last_fail"] = time.time()
                if stats["downtime_start"] is None:
                    stats["downtime_start"] = time.time()

        if status != prev:
            if status == "ok":
                log(f"✅  /health/readiness → {label}", "green")
            elif status == "fail":
                log(f"❌  /health/readiness → {label}", "red")
            else:
                log(f"🔴  /health/readiness → {label}", "red")
            prev = status
        elif status == "ok" and consecutive_ok % 20 == 0:
            log(f"    ✅ still healthy ({consecutive_ok} polls, {consecutive_ok * POLL_INTERVAL:.0f}s)", "gray")

        time.sleep(POLL_INTERVAL)


def _check_health(local_port: int):
    url = f"http://localhost:{local_port}/health/readiness"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            body = resp.read().decode()[:120]
            return "ok", f"200 OK  {body}"
    except urllib.error.HTTPError as e:
        return "fail", f"HTTP {e.code}"
    except Exception as e:
        return "down", f"unreachable ({type(e).__name__}: {e})"


# ── pod watcher ───────────────────────────────────────────────────────────────

def pod_watcher(namespace: str) -> None:
    cmd = [
        "kubectl", "get", "pods",
        "-n", namespace,
        "-l", POD_LABEL,
        "--watch", "--no-headers",
        "-o", "custom-columns="
              "NAME:.metadata.name,"
              "READY:.status.containerStatuses[0].ready,"
              "STATUS:.status.phase,"
              "RESTARTS:.status.containerStatuses[0].restartCount",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while not stop_event.is_set():
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line:
            color = "green" if "true" in line.lower() else "cyan"
            log(f"🔵 POD    {line}", color)
    proc.terminate()


# ── rollout status watcher ────────────────────────────────────────────────────

def rollout_watcher(namespace: str) -> None:
    cmd = [
        "kubectl", "rollout", "status",
        f"deployment/{SERVICE}",
        "-n", namespace,
        "--watch",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while not stop_event.is_set():
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line:
            color = "green" if "successfully" in line.lower() else "yellow"
            log(f"🚀 ROLLOUT {line}", color)
    proc.terminate()


# ── event watcher ─────────────────────────────────────────────────────────────

def event_watcher(namespace: str) -> None:
    cmd = [
        "kubectl", "get", "events",
        "-n", namespace,
        "--watch", "--no-headers",
        "--field-selector", "involvedObject.kind=Pod",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while not stop_event.is_set():
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        keywords = ("litellm", "readiness", "liveness", "startup", "probe", "unhealthy", "backoff")
        if line and any(k in line.lower() for k in keywords):
            color = "red" if any(k in line.lower() for k in ("unhealthy", "backoff", "failed")) else "yellow"
            log(f"📋 EVENT  {line}", color)
    proc.terminate()


# ── inference test ────────────────────────────────────────────────────────────

def inference_test(local_port: int, api_key: str) -> None:
    model = "nvidia/nemotron-3-super-120b-a12b"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: pong"}],
        "max_tokens": 10,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"http://localhost:{local_port}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            elapsed = time.time() - t0
            body = json.loads(resp.read().decode())
            content = body["choices"][0]["message"]["content"].strip()
            log(f"🧪 INFER  OK in {elapsed:.2f}s  model={model}  reply='{content}'", "green")
    except Exception as e:
        elapsed = time.time() - t0
        log(f"🧪 INFER  FAILED in {elapsed:.2f}s  {e}", "red")


# ── port-forward ──────────────────────────────────────────────────────────────

def setup_port_forward(namespace: str, local_port: int) -> subprocess.Popen:
    cmd = [
        "kubectl", "port-forward",
        f"svc/{SERVICE}", f"{local_port}:{SERVICE_PORT}",
        "-n", namespace,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)
    if proc.poll() is not None:
        err = proc.stderr.read().decode()
        log(f"❌ port-forward failed: {err}", "red")
        return None
    log(f"🔌 port-forward  localhost:{local_port} → svc/{SERVICE}:{SERVICE_PORT}", "cyan")
    return proc


# ── summary ───────────────────────────────────────────────────────────────────

def print_summary(start_time: float) -> None:
    elapsed = time.time() - start_time
    with stats_lock:
        s = dict(stats)

    print()
    log("═" * 50, "bold")
    log("  SUMMARY", "bold")
    log("═" * 50, "bold")
    log(f"  Duration      : {elapsed:.1f}s")
    log(f"  Health polls  : {s['total']} total  ✅{s['ok']} ok  ❌{s['fail']} fail")
    avail = (s["ok"] / s["total"] * 100) if s["total"] else 0
    color = "green" if avail >= 99 else "yellow" if avail >= 90 else "red"
    log(f"  Availability  : {avail:.2f}%", color)
    log(f"  Total downtime: {s['total_downtime']:.1f}s")
    if s["first_ok"]:
        log(f"  First healthy : +{s['first_ok'] - start_time:.1f}s after monitor start")
    log("═" * 50, "bold")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LiteLLM rolling-update health monitor")
    parser.add_argument("--namespace",  default=NAMESPACE)
    parser.add_argument("--local-port", type=int, default=LOCAL_PORT)
    parser.add_argument("--api-key",    default="", help="LiteLLM master key (enables inference test)")
    parser.add_argument("--no-events",  action="store_true", help="Suppress event watcher output")
    args = parser.parse_args()

    start_time = time.time()

    def handle_sigint(sig, frame):
        log("\n🛑 Stopping monitor...", "yellow")
        stop_event.set()
        print_summary(start_time)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    log("═" * 50, "bold")
    log("  LiteLLM Rolling-Update Monitor", "bold")
    log("═" * 50, "bold")
    log(f"  namespace : {args.namespace}")
    log(f"  service   : {SERVICE}:{SERVICE_PORT}")
    log(f"  local     : localhost:{args.local_port}")
    log(f"  interval  : {POLL_INTERVAL}s")
    log("  Press Ctrl+C to stop and print summary")
    log("═" * 50, "bold")
    print()

    pf_proc = setup_port_forward(args.namespace, args.local_port)
    if not pf_proc:
        sys.exit(1)

    # ── initial inference baseline (if key provided) ──────────────────────────
    if args.api_key:
        log("🧪 Running baseline inference test before rollout...", "cyan")
        inference_test(args.local_port, args.api_key)
        print()

    # ── start background threads ──────────────────────────────────────────────
    threads = [
        threading.Thread(target=health_poller,  args=(args.local_port,),  daemon=True),
        threading.Thread(target=pod_watcher,    args=(args.namespace,),   daemon=True),
        threading.Thread(target=rollout_watcher, args=(args.namespace,),  daemon=True),
    ]
    if not args.no_events:
        threads.append(threading.Thread(target=event_watcher, args=(args.namespace,), daemon=True))

    for t in threads:
        t.start()

    log("⏳ Monitoring — apply your ArgoCD / kubectl changes now", "yellow")
    print()

    # ── wait loop: re-run inference test every 30s if key provided ────────────
    last_infer = time.time()
    try:
        while not stop_event.is_set():
            time.sleep(1)
            if args.api_key and (time.time() - last_infer) >= 30:
                print()
                log("🧪 Periodic inference check...", "cyan")
                inference_test(args.local_port, args.api_key)
                last_infer = time.time()
    finally:
        stop_event.set()
        pf_proc.terminate()
        print_summary(start_time)


if __name__ == "__main__":
    main()
