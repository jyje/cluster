# ingress-nginx removal record

Tracking issues: #326 (the move to Higress) and #207. This page records which resources were removed when ingress-nginx was replaced by Higress, what was kept on purpose, what Argo CD does not clean up by itself, and how to check that nothing is left. The design and the reasons are in [envoy-gateway-migration.md](../networks/envoy-gateway-migration.md).

## What was removed

| Where | Removed |
|---|---|
| Argo CD | The Applications `ingress-nginx`, `hermes-henry-route` and, for web traffic, the Envoy Gateway web routes of Homer, error-pages and Gameplane |
| `kube-system` | The ingress-nginx DaemonSet and its pods, its Services, ConfigMap, RBAC, IngressClass `nginx` and the admission webhook |
| cert-manager | The ClusterIssuers `nginx-letsencrypt-stag` and `nginx-letsencrypt-prod` |
| MetalLB | The pool of the nodes' own addresses and its advertisement |
| Envoy Gateway | The `envoy-web` GatewayClass, EnvoyProxy, Gateway and proxy, and the watch roles of four namespaces. The controller now watches only `envoy-gateway-system` and `gameplane-games` |
| Higress | The evaluation objects: echo, whoami and httpbin backends, every test Ingress, the self-signed TLS check, the bridge test and the staging probe |
| Repository | The `ingress-nginx` Application, the compatibility test scripts and the retired Traefik page |
| Cluster | The empty namespace `traefik-henry-pilot` |

## What was kept on purpose

- The vendored charts `helm/ingress` (ingress-nginx) and `helm/traefik`. Nothing deploys them, and their rows in `helm/README.md` say so.
- The MetalLB pools in use (the web one and the game one). They live in the environment's private configuration, not in git, so Argo CD never managed or removed them.
- Envoy Gateway for the game UDP Gateway, and the `topology-injector` webhook that Envoy Gateway itself needs.
- The old Istio ClusterIssuers, which are unused but were not part of this move.
- The `gameplane-envoy` Certificate. It is the certificate of the Gameplane host, and its name is historical.

## What Argo CD does not clean up

Argo CD removes only what it manages, and a Certificate's secret, an ACME account key and leader election objects are none of that. These were left behind and were deleted by name:

- In `kube-system`: the secret `ingress-nginx-admission` (webhook certificate), the Lease `ingress-nginx-leader`, and the secrets `nginx-letsencrypt-prod` and `nginx-letsencrypt-stag` (the ACME account keys of the removed issuers).
- The TLS secrets of Certificates that were removed: `error-pages-envoy-tls`, `homer-envoy-tls`, `acme-probe-staging` and `c-tls`.

When an Application is removed from the app-of-apps, the root does not prune it, because the root does not prune by design. Remove such an Application on its own, with its resources, and never prune the root.

## Check that nothing is left

Nothing should print for the checks below, except where noted.

```bash
kubectl get ingress -A -o json | jq -r '.items[] | select(.spec.ingressClassName != "higress") | .metadata.namespace + "/" + .metadata.name'
```

```bash
kubectl get ingressclass,validatingwebhookconfiguration,clusterrole,clusterrolebinding --no-headers | grep -i nginx
```

```bash
kubectl -n kube-system get deploy,ds,svc,cm,secret,sa,role,rolebinding,job,pdb,lease --no-headers | grep -i nginx
```

```bash
kubectl get certificate -A -o json | jq -r '.items[] | select(.spec.issuerRef.name | test("nginx")) | .metadata.namespace + "/" + .metadata.name'
```

```bash
kubectl get secret -A --no-headers | grep -E "envoy-tls|acme-probe"
```

Only `gameplane-system/gameplane-envoy-tls` is expected from the last check, because the Gameplane Ingress uses it.

## Before removing a controller the next time

1. List the Ingresses and Certificates that still use it, and move them first. Move Ingresses in place so that the Certificate each one owns is not deleted.
2. Check that no LoadBalancer Service lands in a pool of node addresses.
3. Delete the Application with its resources on its own, then prune the issuers and pools by name.
4. Run the checks above, and request every public host before and after each step.
