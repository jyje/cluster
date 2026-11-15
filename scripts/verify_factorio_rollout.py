#!/usr/bin/env python3
"""Verify the Factorio rollout and collect a save-continuity fingerprint."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class VerificationError(Exception):
    """An error that is safe to display without exposing cluster addresses."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def current_true(obj, conditions, kind):
    return any(
        condition["type"] == kind and condition["status"] == "True"
        and condition.get("observedGeneration") == obj["metadata"]["generation"]
        for condition in conditions
    )


def check_app(app, revision):
    status = app["status"]
    operation = status.get("operationState", {})
    require(
        not app.get("operation") and operation.get("phase") == "Succeeded"
        and operation.get("syncResult", {}).get("revision") == revision
        and status["sync"]["status"] == "Synced" and status["sync"]["revision"] == revision
        and status["health"]["status"] == "Healthy",
        "Factorio is not Healthy and Synced at the exact requested revision.",
    )


def check_service(service):
    spec = service["spec"]
    ports = spec["ports"]
    require(
        spec["type"] == "ClusterIP" and len(ports) == 1
        and ports[0]["port"] == ports[0]["targetPort"] == 34197
        and ports[0]["protocol"] == "UDP",
        "The Factorio backend Service is not exactly ClusterIP with UDP 34197.",
    )


def check_volume(claim, volume):
    options = set(claim["metadata"]["annotations"]["argocd.argoproj.io/sync-options"].split(","))
    spec = volume["spec"]
    require(
        claim["status"]["phase"] == "Bound" and {"Prune=false", "Delete=false"} <= options
        and spec["persistentVolumeReclaimPolicy"] == "Retain"
        and spec["claimRef"]["uid"] == claim["metadata"]["uid"],
        "The game claim and the matching bound volume are not both protected.",
    )


def check_gateway(gateway, route):
    require(
        current_true(gateway, gateway["status"]["conditions"], "Programmed"),
        "The game Gateway is not Programmed at its current generation.",
    )
    parents = [
        parent for parent in route["status"].get("parents", [])
        if parent["controllerName"] == "gateway.envoyproxy.io/gatewayclass-controller"
        and parent["parentRef"].get("name") == "factorio"
        and parent["parentRef"].get("namespace") == "envoy-gateway-system"
        and parent["parentRef"].get("sectionName") == "game"
    ]
    require(
        len(parents) == 1 and all(current_true(route, parents[0]["conditions"], condition)
                                  for condition in ("Accepted", "ResolvedRefs")),
        "The Factorio UDPRoute is not accepted with resolved references by the game listener.",
    )


def check_restart(before, after):
    require(before["revision"] == after["revision"], "The rollout revision changed during the test.")
    require(before["pod_uid"] != after["pod_uid"], "The Factorio Pod has not been replaced.")
    require(
        (before["claim_uid"], before["volume_uid"]) == (after["claim_uid"], after["volume_uid"]),
        "The Factorio claim or volume was replaced.",
    )
    require(
        bool(set(before["save_hashes"]) & set(after["save_hashes"])),
        "No pre-restart save fingerprint remains on the volume.",
    )


def run(context, revision):
    def kubectl(*args):
        try:
            return subprocess.check_output(
                ["kubectl", "--context", context, "--request-timeout=10s", *args],
                text=True, stderr=subprocess.DEVNULL, timeout=20,
            )
        except subprocess.SubprocessError:
            raise VerificationError(f"Could not complete the Kubernetes {args[0]} check.") from None

    def get(kind, name, namespace=None):
        options = ("-n", namespace) if namespace else ()
        return json.loads(kubectl("get", kind, name, *options, "-o", "json"))

    app = get("application", "factorio", "argocd")
    check_app(app, revision)
    check_service(get("service", "factorio", "factorio"))
    claim = get("pvc", "factorio-data", "factorio")
    volume = get("pv", claim["spec"]["volumeName"])
    check_volume(claim, volume)
    check_gateway(
        get("gateway", "factorio", "envoy-gateway-system"),
        get("udproute", "factorio-game", "factorio"),
    )
    # Use the same dedicated-pool verification as the LAN PoC, not a new allocator.
    preflight = Path(__file__).with_name("preflight_envoy_udp_pool.py")
    require(preflight.is_file(), "The reserved-pool preflight from the LAN PoC is missing.")
    result = subprocess.run(
        [sys.executable, str(preflight), context, "--check-gateway"], stdout=sys.stderr, timeout=150,
    )
    require(result.returncode == 0, "The game Service does not pass reserved-pool verification.")

    def ready_pod():
        pods = json.loads(kubectl(
            "get", "pods", "-n", "factorio",
            "-l", "app.kubernetes.io/name=factorio,app.kubernetes.io/instance=factorio,pod.name=main",
            "-o", "json",
        ))["items"]
        require(
            len(pods) == 1 and not pods[0]["metadata"].get("deletionTimestamp")
            and any(c["type"] == "Ready" and c["status"] == "True" for c in pods[0]["status"]["conditions"]),
            "There is not exactly one running, Ready game Pod.",
        )
        return pods[0]

    pod = ready_pod()
    tag = app["spec"]["source"]["helm"]["valuesObject"]["image"]["tag"]
    require(
        "@sha256:" in tag and any(
            c["name"] == "factorio" and c["image"].endswith(":" + tag)
            for c in pod["spec"]["containers"]
        ),
        "The game Pod does not use the pinned Factorio image.",
    )
    checks = r"""
set -o pipefail
grep -qi ':8595 ' /proc/net/udp /proc/net/udp6
awk '$4 == "0A" {found=1} END {exit found ? 1 : 0}' /proc/net/tcp /proc/net/tcp6
jq -e '.require_user_verification == true and .visibility.public == false' /factorio/server-settings.json >/dev/null
find /factorio/saves -maxdepth 1 -type f -name '*.zip' ! -name '*.tmp.zip' -exec sha256sum {} + | cut -d ' ' -f 1 | sort -u
"""
    hashes = kubectl(
        "exec", pod["metadata"]["name"], "-n", "factorio", "-c", "factorio", "--", "/bin/sh", "-ec", checks,
    ).splitlines()
    require(bool(hashes) and all(re.fullmatch("[a-f0-9]{64}", h) for h in hashes), "No valid save fingerprint was found.")
    require(
        ready_pod()["metadata"]["uid"] == pod["metadata"]["uid"],
        "The game Pod changed during verification; run the check again.",
    )
    return {
        "revision": revision, "pod_uid": pod["metadata"]["uid"],
        "claim_uid": claim["metadata"]["uid"], "volume_uid": volume["metadata"]["uid"],
        "save_hashes": hashes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context")
    parser.add_argument("revision", help="Exact deployed Git commit (40 hex characters)")
    parser.add_argument("--previous", type=Path, help="Local JSON snapshot from before the Pod replacement")
    args = parser.parse_args()
    try:
        require(re.fullmatch("[a-f0-9]{40}", args.revision), "Provide the full deployed Git revision.")
        result = run(args.context, args.revision)
        if args.previous:
            check_restart(json.loads(args.previous.read_text()), result)
            print("PASS: replacement Pod kept the same protected volume and a save fingerprint", file=sys.stderr)
        print("Game client join and in-game state continuity must be verified separately.", file=sys.stderr)
    except VerificationError as error:
        raise SystemExit(f"FAIL: {error}") from None
    except (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.SubprocessError):
        raise SystemExit("FAIL: could not verify the live Factorio rollout.") from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
