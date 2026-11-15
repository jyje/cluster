# Envoy Gateway cutover and Factorio

Do not sync this change until the live UDP echo proof of concept for
[#274](https://github.com/jyje/cluster/issues/274) has passed before and after
replacement of the echo Pod. Leave legacy ingress-nginx routes unchanged.

The game Gateway stays on ClusterIP in this draft. Before rollout, carry
forward the exact reserved LoadBalancer allocation that passed the live UDP
proof. Do not use an automatically selected address from a shared pool.

When submitting a manual sync directly through the Kubernetes Application
resource, copy `spec.syncPolicy.syncOptions` into
`operation.sync.syncOptions`. Argo CD's CLI/API does this by default. Without
it, CRDs that require server-side apply can exceed the annotation size limit.

1. Inventory live and declared Traefik routes. The Henry pilot is the known
   GitOps route definition. If further routes exist, add parity checks before
   retiring Traefik.
2. Sync the Factorio app and verify the claim binds, the server is ready, and
   the game Service has only UDP port 34197.
3. Sync Envoy Gateway and verify the controller was replaced and is ready.
   Check the controller watch list and permission scope.
4. Sync the gateway application without prune, then sync the Henry pilot.
   Check current Gateway and route conditions. Test the Henry HTTP path and
   verify that existing public ingress-nginx paths still work.
5. Join with a Factorio 2.1.24 client and make a recognizable change. Wait for
   an autosave, replace the game Pod, and reconnect to verify the same world
   and change are still present. Verify there is no RCON Service or listener.
6. Only after the checks pass, prune the old echo Deployment, Service, and
   UDPRoute and remove Traefik in a separate cleanup change. Do not prune the
   Gateway API CRDs, the Envoy game Gateway, or the Factorio data claim.

For rollback, record the last working revision before the cutover. Restore and
sync the previous routing and namespace watch configuration before retiring
any old controller or backend. Confirm an echo round trip and any previously
active Traefik routes. Leave the shared Gateway API CRDs and Factorio data claim
in place.
