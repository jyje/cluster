#!/usr/bin/env python3
"""Verify a pre-reserved, private PoC address without printing it."""

import argparse
import ipaddress as ip
import json
import socket
import subprocess
from urllib.parse import urlsplit


POOL = "factorio-private"
NAMESPACE = "envoy-gateway-system"
LABEL = "networking.jyje.io/reserved-vip"
POOL_KEYS = ("metallb.io/address-pool", "metallb.universe.tf/address-pool")
IP_KEYS = ("metallb.io/loadBalancerIPs", "metallb.universe.tf/loadBalancerIPs")
LEGACY_CONTROLLER = "quay.io/metallb/controller:v0.13.3"
PRIVATE = tuple(map(ip.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))


class PreflightError(ValueError):
    """A safe, address-free validation error."""


def require(condition, message):
    if not condition:
        raise PreflightError(message)


def contains(entry, candidate):
    if "-" in entry:
        first, last = map(ip.ip_address, entry.split("-", 1))
        return first.version == last.version == candidate.version and first <= candidate <= last
    return candidate in ip.ip_network(entry, strict=False)


def game_service(service):
    metadata = service["metadata"]
    labels = metadata.get("labels", {})
    return (
        metadata.get("namespace") == NAMESPACE
        and labels.get(LABEL) == "factorio"
        and labels.get("gateway.envoyproxy.io/owning-gateway-name") == "factorio"
        and labels.get("gateway.envoyproxy.io/owning-gateway-namespace") == NAMESPACE
        and all(metadata.get("annotations", {}).get(key) == POOL for key in POOL_KEYS)
    )


def external_ips(service):
    return [i.get("ip") for i in service.get("status", {}).get("loadBalancer", {}).get("ingress", [])]


def preflight(pools, advertisements, nodes, services, networks, api_addresses, controller_image=None):
    targets = [pool for pool in pools if pool["metadata"]["name"] == POOL]
    require(len(targets) == 1, "The dedicated IPAddressPool has not been provisioned.")
    spec = targets[0]["spec"]
    require(spec.get("autoAssign") is False, "The dedicated pool must disable auto-assignment.")
    if "serviceAllocation" not in spec:
        require(
            controller_image == LEGACY_CONTROLLER,
            "A selectorless pool is supported only on the verified legacy MetalLB version.",
        )
    else:
        require(
            spec["serviceAllocation"] == {
                "namespaces": [NAMESPACE],
                "serviceSelectors": [{"matchLabels": {LABEL: "factorio"}}],
            },
            "The dedicated pool must permit only the labeled game Service.",
        )
    entries = spec.get("addresses", [])
    require(len(entries) == 1, "The dedicated pool must contain one IPv4 /32.")
    reserved = ip.ip_network(entries[0], strict=True)
    require(
        reserved.version == 4 and reserved.prefixlen == 32
        and any(reserved.subnet_of(network) for network in PRIVATE),
        "The dedicated pool must contain one RFC1918 IPv4 /32.",
    )
    candidate = reserved.network_address
    for pool in pools:
        if pool["metadata"]["name"] != POOL:
            require(
                not any(contains(entry, candidate) for entry in pool["spec"]["addresses"]),
                "The dedicated address overlaps another MetalLB pool.",
            )
    require(
        any(POOL in ad["spec"].get("ipAddressPools", []) for ad in advertisements),
        "No L2Advertisement explicitly references the dedicated pool.",
    )
    require(candidate not in api_addresses, "The dedicated address matches the API endpoint.")
    for node in nodes:
        require(
            not any(
                candidate == ip.ip_address(entry["address"])
                for entry in node.get("status", {}).get("addresses", [])
                if entry.get("type") in {"InternalIP", "ExternalIP"}
            ),
            "The dedicated address is assigned to a Kubernetes node.",
        )
    require(
        not any(contains(network, candidate) for network in networks),
        "The dedicated address overlaps a Pod or Service network.",
    )
    for service in services:
        if game_service(service):
            continue
        spec = service["spec"]
        annotations = service["metadata"].get("annotations", {})
        require(
            not any(annotations.get(key) == POOL for key in POOL_KEYS),
            "Another Service explicitly requests the dedicated pool.",
        )
        requested = [value.strip() for key in IP_KEYS for value in annotations.get(key, "").split(",")]
        assigned = (
            spec.get("clusterIPs", [])
            + spec.get("externalIPs", [])
            + [spec.get("clusterIP"), spec.get("loadBalancerIP")]
            + requested
            + external_ips(service)
        )
        require(str(candidate) not in assigned, "The dedicated address is already requested or in use.")
    return candidate


def check_gateway(services, gateway, candidate):
    game = [service for service in services if game_service(service)]
    address = str(candidate)
    require(
        len(game) == 1 and game[0]["spec"]["type"] == "LoadBalancer" and external_ips(game[0]) == [address],
        "The generated game Service does not have exactly the dedicated address.",
    )
    require(
        gateway.get("status", {}).get("addresses") == [{"type": "IPAddress", "value": address}],
        "The Gateway does not advertise exactly the dedicated address.",
    )


def run(context, verify_gateway):
    def kubectl(*args):
        return json.loads(subprocess.check_output(
            ["kubectl", "--context", context, "--request-timeout=10s", *args, "-o", "json"],
            stderr=subprocess.DEVNULL,
            timeout=20,
        ))

    def items(resource, *args):
        return kubectl("get", resource, *args)["items"]

    endpoint = kubectl("config", "view", "--minify")["clusters"][0]["cluster"]["server"]
    hostname = urlsplit(endpoint).hostname
    require(hostname, "The API endpoint could not be verified.")
    api_addresses = {ip.ip_address(row[4][0]) for row in socket.getaddrinfo(hostname, None)}
    pool_ns = ("-n", "metallb-system")
    networks = [
        cidr for resource in items("servicecidrs.networking.k8s.io")
        for cidr in resource["spec"]["cidrs"]
    ] + [resource["spec"]["cidr"] for resource in items("ippools.crd.projectcalico.org")]
    services = items("services", "-A")
    controllers = [
        container["image"]
        for item in items("deployments", *pool_ns)
        if item["status"].get("availableReplicas", 0) > 0
        for container in item["spec"]["template"]["spec"]["containers"]
        if container["name"] == "controller"
    ]
    controller_image = controllers[0] if len(controllers) == 1 else None
    candidate = preflight(
        items("ipaddresspools.metallb.io", *pool_ns),
        items("l2advertisements.metallb.io", *pool_ns),
        items("nodes"),
        services,
        networks,
        api_addresses,
        controller_image,
    )
    if verify_gateway:
        check_gateway(services, kubectl("get", "gateway", "factorio", "-n", NAMESPACE), candidate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context", help="Kubernetes context to check")
    parser.add_argument("--check-gateway", action="store_true", help="Also verify the live allocation")
    args = parser.parse_args()
    try:
        run(args.context, args.check_gateway)
    except PreflightError as exc:
        raise SystemExit(f"FAIL: {exc}") from None
    except (ValueError, TypeError, KeyError, IndexError, OSError, subprocess.SubprocessError):
        # Malformed network data and subprocess exceptions can contain private addresses.
        raise SystemExit("FAIL: Could not validate the live network configuration.") from None
    print("PASS: dedicated pool, service scope, and live Kubernetes address exclusions")


if __name__ == "__main__":
    main()
