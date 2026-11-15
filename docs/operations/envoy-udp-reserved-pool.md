# Dedicated address for the Envoy UDP proof of concept

Keep the PoC on ClusterIP until a LAN operator has confirmed a usable static
IPv4 address in the authoritative DHCP/IPAM configuration. It must be outside
the DHCP lease range and other address pools, not assigned to another device,
and reachable from the intended test network. A lack of ping or ARP replies
does not establish that an address is reserved.

Provision the following resources through the environment's private
configuration. Replace the placeholder privately; do not commit a real
address to this repository. Do not change the shared pool or its advertisement.

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: factorio-private
  namespace: metallb-system
spec:
  autoAssign: false
  addresses:
    - RESERVED_IPV4/32
  serviceAllocation:
    namespaces:
      - envoy-gateway-system
    serviceSelectors:
      - matchLabels:
          networking.jyje.io/reserved-vip: factorio
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: factorio-private
  namespace: metallb-system
spec:
  ipAddressPools:
    - factorio-private
```

Before syncing the PoC change, run
`python3 scripts/preflight_envoy_udp_pool.py <context>`. This checks the live
pool and service restriction, API and node addresses, other pools, and Pod,
Service, and LoadBalancer allocations. It does not verify the DHCP reservation;
that check must come from the network operator.

Then sync the PoC and run `bash scripts/verify_envoy_udp_poc.sh <context>`
from a client on the intended LAN. Require the Gateway to be programmed, the
route to be accepted with resolved references, and three successful UDP
round trips. Replace the echo Pod, then repeat using the previous UID
reported by the verifier. Keep the old ingress controllers unchanged.

For rollback, restore the PoC's ClusterIP configuration through GitOps,
confirm the generated Service no longer has an external address, then remove
the dedicated pool only when nothing uses it.
