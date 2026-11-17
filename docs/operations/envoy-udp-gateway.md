# UDP game Gateway

The `games` Gateway in `envoy-gateway-system` carries public game traffic to a
server that Gameplane runs. The Gateway, its proxy and the route are in
`manifests/envoy-gateways/`. The server itself is created in the dashboard (see
[gameplane.md](gameplane.md)).

## Path

WAN UDP port, forwarded by the router, then a LoadBalancer address from a
dedicated MetalLB pool, then the Envoy proxy of the `games` Gateway, then a
`UDPRoute` in `gameplane-games`, then the Service of the game server. The
public name is a CNAME to the router's DDNS host, like the other
`app.jyje.online` names. The router forward is outside Git.

## The address pool

The pool is private configuration and is not in this repository. It holds one
reserved LAN address, outside the DHCP range and the other pools, with
`autoAssign: false`, and the proxy Service names it with an annotation. Never
use the default pool for a game Service: it holds the node addresses, and a node
address on a Service caused an ARP conflict before.

MetalLB v0.13.3 does not support `serviceAllocation`, so it does not restrict
which Service may take the pool. It honors the legacy
`metallb.universe.tf/address-pool` key, and the manifest sets both that and the
current key. Reinstate a selector restriction before upgrading the controller.

### Renaming the pool

A MetalLB pool cannot be renamed, and two pools cannot hold the same address, so
a rename is a manual step outside Git. Why: the name must not describe what the
Service carries. The reserved address is released for a short time, so expect
the public UDP port to be down for one to three minutes. Do it when nobody is
online.

1. Merge the change that updates both annotations in `games-gateway.yaml`. The
   `envoy-udp-poc` Application is a manual sync, so nothing changes yet.
2. Save the old `IPAddressPool` and `L2Advertisement`, rename them in the saved
   copy, and replace `ipAddressPools` in the `L2Advertisement` with the new name.
   Delete the old pair and apply the new pair in one go.
3. Sync `envoy-udp-poc`. The proxy Service takes the same address again.
4. Check with `kubectl get svc -n envoy-gateway-system` that the `EXTERNAL-IP`
   is the reserved address, then join the game once.

Example with placeholder values (use your own address and names):

```bash
kubectl -n metallb-system get ipaddresspool old-pool -o yaml > pool.yaml
# edit: metadata.name -> new-pool, spec.addresses stays "192.0.2.10/32"
kubectl -n metallb-system delete ipaddresspool,l2advertisement old-pool
kubectl apply -f pool.yaml
```

## Placement

The proxy must not run on the 4 KB page nodes (`raspi.type: 4b`): Envoy's
TCMalloc cannot map its heap there and crashes at start. The game server itself
should run on a `5b` node. See [node-labels.md](node-labels.md).

## Namespaces

The Envoy controller watches only the namespaces listed in the `envoy-gateway`
Application, so `gameplane-games` is on that list. The listener accepts routes
from that namespace only.

## Change the server behind the route

Edit `backendRefs` in `games-route.yaml` to the Service name of the new server,
and sync `envoy-udp-poc`. The Application keeps its old name so the existing
Gateway stays tracked. Check that the route is `Accepted` with resolved
references, then join from a client.

## Rollback

Point `backendRefs` back at the previous Service and sync. The address, the
router forward and the DNS name do not change.
