# Envoy Gateway UDP proof of concept

This is the first deployment phase of [#274](https://github.com/jyje/cluster/issues/274).
It does not deploy Factorio, change a Traefik route, or retire ingress-nginx.

## Sync order

1. Sync `envoy-gateway-crds` and wait for the Envoy-specific CRDs to be
   established. The existing `gateway-api` Application remains the sole owner
   of the shared Gateway API CRDs.
2. Sync `envoy-gateway` and wait for the controller Deployment to be available.
   Its watch and Secret read access are scoped to its own namespace.
3. Sync `envoy-udp-poc`. Wait for the echo Deployment to be ready. Confirm the
   `factorio` Gateway is `Programmed=True`, the UDP listener is programmed,
   and the `factorio` UDPRoute reports `Accepted=True` and
   `ResolvedRefs=True` for that listener.

The apps are manual-sync on purpose. Use an approved private MetalLB address
pool and do not add WAN port forwarding for this proof of concept.

## Connectivity gate

From a client on the intended network with read-only cluster access, run
`bash scripts/verify_envoy_udp_poc.sh <context>`. It checks current Gateway
and route conditions, then verifies three UDP round trips to the advertised
address. Record the returned echo Pod UID. After an approved restart, wait
for the replacement Pod and rerun with the previous UID as the second
argument. Check the current web paths again before proceeding.

On a client without cluster access, use
`python3 scripts/probe_envoy_udp_poc.py <gateway-address>` and check the
Gateway conditions and Pod replacement separately.

Use a real Factorio client to validate the next phase; the echo probe does
not validate game traffic, reconnects, or save persistence.

## Rollback

Remove only the PoC resources, including the dedicated Gateway. Confirm its
generated LoadBalancer Service is gone and the original web paths still work.
If the Envoy controller must also be removed, do so after the PoC resources,
without deleting the shared Gateway API CRDs.
