# Moving web traffic to Higress

Tracking issues: #207, #314 (the evaluation) and #326 (the move). This page records how web traffic moved from ingress-nginx to Higress, what changed for the apps, and how the cluster is set up now. The file keeps its old name because other pages link to it.

## Where things stand

- **Higress** is the ingress controller for every public host (17 Ingresses). It runs as a Deployment with one gateway pod on each worker node (the control plane node is left out), behind a LoadBalancer Service with `externalTrafficPolicy: Local`.
- **The entry point** is the router's port-forward of ports 80 and 443 to the Higress address. The address comes from a MetalLB pool named `web-private` that lives outside this repository, in the environment's private configuration. The repository holds only the pool name, never the address.
- **ingress-nginx is gone**, together with its issuers and the MetalLB pool of node addresses.
- **Envoy Gateway** stays for games and any UDP only (the `games` Gateway). Higress has no UDP listener, which was checked on the live gateway.

## Why Higress and not Envoy Gateway for the web

Envoy Gateway handles only Gateway API, not Ingress, so it cannot read the `nginx.ingress.kubernetes.io/*` annotations that the apps used. Higress is Envoy based, reads most of those annotations as they are, and also supports Gateway API. That kept the move small: most Ingresses changed only their class and issuer.

## Annotation mapping

| nginx annotation | On Higress |
|---|---|
| `enable-cors`, `cors-allow-*` | The same name works |
| `affinity`, `session-cookie-*` | The same name works |
| `proxy-read-timeout`, `proxy-send-timeout` | Not used. The gateway-wide `downstream.idleTimeout` (3600 seconds) covers it |
| `limit-rps` | Renamed to `higress.io/route-limit-rps`. It limits per route, not per client |
| `ssl-redirect` | The same name works, and is needed (Higress did not redirect HTTP to HTTPS by default) |
| `limit-connections`, `proxy-body-size` | No equivalent. Any request size passes |
| `configuration-snippet` (CORS origin echo) | An explicit `cors-allow-origin` |
| `custom-http-errors` | Not supported. See below |

Two settings are easy to miss. The Higress gateway closes any connection that carries no data for 180 seconds by default, whatever the route timeout is, so `downstream.idleTimeout` is raised to 3600. And Higress does not redirect HTTP to HTTPS unless `ssl-redirect` is set.

## What users see differently

- Error responses now come from the apps. ingress-nginx replaced responses with the status codes 401, 403, 404, 405, 408, 409, 410, 429, 500, 502, 503 and 504 by the screens of the `error-pages` service. Higress passes the app's own response through. The `error-pages` service still runs and has its own host, but nothing sends traffic to it as a default backend.
- There is no cap on request body size and no cap on connections per client any more. The Ingresses that had a cap are behind authentication.
- Rate limiting is per route, not per client.

## Certificates

The ClusterIssuers `higress-letsencrypt-stag` and `higress-letsencrypt-prod` use `ingressClassName: higress` for the HTTP-01 challenge Ingress. Every Certificate was reissued through the production issuer when the Ingresses moved to Higress, and the first staging issuance through Higress took 31 seconds. A certificate renews through Higress only because the public port 80 reaches Higress, so a router rule that points port 80 anywhere else stops renewals.

## How the move was done, and what to reuse

The router forwards by port, so it cannot split hosts. The plan of moving host by host with a bridge (an nginx Ingress that passes the host to Higress) was tried for two dev hosts. It works, with three rules:

1. Pass the request to Higress over HTTPS. A plain HTTP hop makes Higress rewrite `X-Forwarded-Proto` to `http`.
2. Set `proxy-ssl-secret` together with the SNI settings. Without a secret, ingress-nginx ignores `proxy-ssl-name` and the SNI switch, sends no SNI, and Higress resets the handshake. The first try failed with a 502 for exactly this reason.
3. Keep the limits that still make sense on the bridge, such as the body size.

In the end the move was done at once. Every host got a Higress Ingress first (a copy of the nginx one, checked through the Higress address with its real name), then the router was switched, then every Ingress was changed in place from `nginx` to `higress`. In place matters: the Certificate that cert-manager created for an Ingress is owned by it, so recreating the Ingress would delete the Certificate.

Checks that were worth their cost: compare status, certificate, body and redirect of every host between the old and the new path, request a unique path and find it in the new gateway's log, and watch the public hosts every half second during each change. The tests are described in #314 and #326.

## Limits to know

- The gateway needs a worker node. The control plane node does not run one, and with three workers, losing one leaves two pods.
- The address is announced by one node at a time, chosen among the nodes that run a ready gateway pod. A change of the announcing node can drop connections for a few seconds.
- The pool of the web address must hold an address that no node owns. A pool that overlaps node addresses caused an ARP conflict before (see [cluster-design.md](../architecture/cluster-design.md)).

## Rollback

ingress-nginx is removed from git. To go back, restore its manifests from the git history before the removal, change the Ingresses back to `nginx` with the nginx issuers, and point the router at the nodes again. The Higress and ingress-nginx setups do not share state, so both directions are a configuration change.
