# Shared Traefik Gateway

This is the next step in [#207](https://github.com/jyje/cluster/issues/207).
The shared edge has two independent, manual-sync Argo CD Applications:

| Application | Owns |
| --- | --- |
| `traefik-shared` | Traefik, its ServiceAccount and RBAC, GatewayClass, and shared Gateway |
| `hermes-henry-route` | Only the Henry HTTPRoute, in the existing Henry namespace |

The shared listener is internal-only. It uses a ClusterIP Service and an
test-only hostname, not public DNS, TLS, or a node port. This replaces the
original pilot from #208 without changing Henry's production Ingress or OIDC
configuration. Neither Application enrolls any workload in Istio Ambient.

## Access boundaries

The [pinned Traefik Gateway provider](https://github.com/traefik/traefik/blob/v3.7.17/pkg/provider/kubernetes/gateway/client.go)
watches Namespace and GatewayClass objects cluster-wide. Its ServiceAccount
can update only the shared GatewayClass's status at cluster scope. The
namespaced ClusterRole is bound only through RoleBindings in the platform and
approved application namespaces. Do not bind it with a ClusterRoleBinding.

The pinned provider starts a Secret informer in every watched namespace, even
for an HTTP-only Gateway. The account can therefore read Secrets in those
namespaces, but must not be able to list Secrets cluster-wide or read Secrets
in any other namespace. The GatewayClass selector and Gateway allowlist
limit reconciliation, not API authorization.

When onboarding another namespace, review its Secret exposure first, then
update the provider's namespace list, listener namespace selector, and
RoleBindings together. The application team manages its own HTTPRoute.

## Rollout and checks

1. Confirm the standard Gateway API bundle is synced. Manually sync
   `traefik-shared`, then check GatewayClass `Accepted=True` and Gateway
   `Programmed=True`. The platform Application creates its own Namespace
   before the other resources using a sync wave.
2. Verify the ServiceAccount's effective permissions using an administrator
   context. The expected answers are `yes`, `yes`, `no`, and `no`:

   ```sh
   sa=system:serviceaccount:traefik-system:traefik-shared
   can_i() {
     kubectl --context microk8s auth can-i --as="$sa" \
       --as-group=system:authenticated \
       --as-group=system:serviceaccounts \
       --as-group=system:serviceaccounts:traefik-system "$@"
   }
   can_i list secrets -n traefik-system
   can_i list secrets -n hermes-agent-henry
   can_i list secrets --all-namespaces
   can_i get secrets -n kube-system
   ```

3. Manually sync `hermes-henry-route`. Confirm the HTTPRoute has
   `Accepted=True` and `ResolvedRefs=True` for the shared Gateway.
4. Port-forward the shared Service to loopback, then test the route without
   following redirects or sending credentials:

   ```sh
   kubectl --context microk8s -n traefik-system \
     port-forward --address localhost svc/traefik-shared 18080:80
   ```

   ```sh
   curl -sS -D - -o /dev/null -H 'Host: henry.gateway.invalid' http://localhost:18080/
   curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: henry.gateway.invalid' http://localhost:18080/api/auth/me
   ```

   Expect a sign-in redirect for the root and `404` for the unmatched API
   path. The existing production ingress should continue to respond unchanged.

## Retire the original pilot

The pilot definition is removed from Git. The parent Application does not
prune automatically, so a previously synced pilot remains live until it is
explicitly deleted. Do not enable pruning on the parent just for this change.

After the parent has reconciled the merged revision and the shared-path checks
above pass, use Argo CD to delete only `traefik-henry-pilot` with foreground
cascading deletion:

```sh
argocd app delete traefik-henry-pilot --cascade --propagation-policy foreground
```

Confirm that the old HTTPRoute, Gateway, GatewayClass, Deployment, Service, and
pilot ClusterRoleBinding are gone. Its manually created namespace can be
removed separately after checking that it has no remaining workloads. Leave
the shared platform, Henry's production Application, and the Gateway API CRDs
in place.

A production traffic cutover still requires HTTPS, OIDC, and
certificate-renewal verification.

## Rollback

Remove the Henry route Application before removing the shared platform
Application. Cascade only their own resources; the dedicated platform
Namespace is retained intentionally and can be removed separately once empty.
Do not remove shared Gateway API CRDs, the Henry workload, or its production
Ingress.
