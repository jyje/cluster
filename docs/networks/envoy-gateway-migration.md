# Envoy Gateway migration

Tracking issue: #207. This page records the design for moving web traffic from ingress-nginx to Envoy Gateway, and the checks to run before the ports are swapped.

## Where things stand

- Envoy Gateway runs in `envoy-gateway-system` with the `envoy-web` Gateway (ClusterIP, no public entry point yet) and the `factorio` Gateway (UDP).
- ingress-nginx still owns ports 80 and 443 on the node network. It serves every public host, so nothing public changes until the cutover.
- The first two apps to move are `homer-instance` (`app.jyje.online`) and `error-pages` (`error.app.jyje.online`), because they are stateless and low risk.

## Design

### Listeners and routes

`envoy-web` has one HTTPS listener per host (`https-app`, `https-error`) on port 8443. Each listener only accepts routes from its own namespace, so an app cannot claim another app's host. The `HTTPRoute` for each app lives next to the app, in its Argo CD Application, and points at the matching listener with `sectionName`.

These routes are dormant: they have the real hostnames, but no traffic reaches the Gateway from outside. The Ingress objects stay in place and keep serving.

The controller only watches namespaces that are listed in the `envoy-gateway` Application. Add a namespace there before its first route.

### Certificates

Certificates are explicit `Certificate` resources in `envoy-gateway-system` (`manifests/envoy-factorio-gateways/certificates.yaml`), not Gateway annotations.

- While ingress-nginx answers port 80, only its HTTP-01 solver can finish a challenge. The Certificates therefore use the existing `nginx-letsencrypt-prod` issuer.
- A Certificate keeps renewing after the old Ingress is removed, so the secret does not depend on the Ingress staying around.
- At the cutover, port 80 moves to Envoy. Then the Certificates switch to an issuer with the Gateway API HTTP-01 solver, and cert-manager gets `config.gatewayAPI.enabled: true`. That change is not made yet because the solver cannot complete a challenge until port 80 points at Envoy, and it would restart cert-manager for no gain.

### Homer cards

homer-operator still runs with `enableGatewayAPI: false`, so cards keep coming from the Ingress annotations. The cutover turns the option on, moves the annotations to the HTTPRoutes, and removes the Ingresses in the same change, so no card is duplicated.

## Check before the cutover

Port-forward the Envoy service and request each host with its real name, so TLS and routing are tested without touching public traffic.

```bash
kubectl -n envoy-gateway-system port-forward \
  $(kubectl -n envoy-gateway-system get svc -l gateway.envoyproxy.io/owning-gateway-name=envoy-web -o name) 8443:8443
```

```bash
curl -sI --resolve app.jyje.online:8443:127.0.0.1 https://app.jyje.online:8443/
```

```bash
curl -sI --resolve error.app.jyje.online:8443:127.0.0.1 https://error.app.jyje.online:8443/
```

Also check that the Gateway reports `Programmed=True`, both listeners report `ResolvedRefs=True` once the certificates are issued, and each route reports `Accepted=True`.

## Cutover outline

1. Enable the cert-manager Gateway API support and add an issuer with the Gateway API solver, then move the two Certificates to it.
2. Add an HTTP listener on the Gateway for the ACME challenge and an HTTP to HTTPS redirect.
3. Free ports 80 and 443 on the nodes (stop the ingress-nginx DaemonSet) and expose Envoy on them. Plan this window, because a short outage is expected.
4. Enable `enableGatewayAPI` in homer-operator and move the Homer annotations to the HTTPRoutes.
5. Remove the Ingresses of the migrated apps, then repeat for the next batch.

## Rollback

Keep the ingress-nginx manifests in git until the new path is verified. To roll back, restore the ingress-nginx DaemonSet on the host ports and point the Cloudflare Tunnel and the router back at it. The Ingress objects and their certificates are untouched until their own removal step, so no data is lost.
