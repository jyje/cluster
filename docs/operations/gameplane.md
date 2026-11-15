# Gameplane

Korean version: [gameplane-ko.md](gameplane-ko.md)

Operating notes for the `gameplane` Application, a Kubernetes-native game
server control panel (https://github.com/GameplanePanel/Gameplane, chart 0.4.0,
pre-v1). Tracking issue: [#301](https://github.com/jyje/cluster/issues/301).
No game server is created yet. Never commit a password, token or private key.

## How it is set up

- One Argo CD Application, `gameplane`, deploys the vendored chart
  (`helm/gameplane/gameplane-0.4.0`) into `gameplane-system`. The chart creates
  `gameplane-games` for future game servers.
- Argo CD syncs the CRDs with the chart using server-side apply, so the chart's
  pre-upgrade CRD hook is off. Removing the Application would prune the CRDs
  and every GameServer with them, so do not delete it once games exist.
- The API keeps its SQLite database on a `2Gi` claim. The cluster's only
  StorageClass is NFS, and SQLite in WAL mode can misbehave on NFS. Watch the
  API logs for database lock errors after the first rollout.
- Anonymous usage telemetry is off (`api.telemetry.enabled: false`).
- The default module source pulls the module catalog from `ghcr.io` every hour.

## Agent mTLS material

The chart can generate its own CA, but Argo CD renders offline, so it would
issue a new CA on every render. The CA and the client certificate are therefore
SealedSecrets in the Application:

| Secret | Keys |
|---|---|
| `gameplane-external-ca-v1` | `ca.crt`, `ca.key` |
| `gameplane-external-client-v1` | `tls.crt`, `tls.key` |

To rotate, create new material, seal it under a new versioned name (`-v2`),
point `api.agentMTLS` at the new names, and let the API and operator roll. The
agents trust the CA, so existing game pods need a restart after a CA change.
The private keys are never kept in the repository, only the sealed form.

## Reaching the dashboard

The public host is `gameplane.app.jyje.online`. The Gateway, Certificate and
HTTPRoute live in the Application (`extraResources`) and join the shared
`envoy-web` class. ingress-nginx still owns ports 80 and 443 on the nodes, so
a small bridge Ingress in the Application terminates TLS with the Certificate
and forwards to the Envoy proxy over HTTPS (through an `ExternalName` Service,
`envoy-web` in `envoy-gateway-system`). The HTTPRoute then sends every path to
`gameplane-web`. Public traffic therefore already passes through Envoy
Gateway. At the cutover described in
[envoy-gateway-migration.md](../networks/envoy-gateway-migration.md), Envoy
takes the ports and the bridge Ingress and Service are removed.

Two details of the bridge matter:

- ingress-nginx replaces some backend errors with its own error pages
  (`custom-http-errors`). The dashboard API answers 401 and 404 itself, and the
  SPA reads them, so the bridge Ingress overrides the list with an unused code.
- The Envoy listener picks its certificate by SNI, so the Ingress sets
  `proxy-ssl-server-name` and `proxy-ssl-name`.

The DNS record is a CNAME to the same DDNS host as the other `app.jyje.online`
names. The Let's Encrypt HTTP-01 challenge needs it before the Certificate can
be issued.

The Homer card is a manual entry in the `4. Games` group of `homer-instance`
(not an Ingress annotation), so it survives the move from the bridge Ingress to
the HTTPRoute.

To check the Envoy path without the public hop, use a port-forward:

```bash
kubectl -n envoy-gateway-system port-forward \
  $(kubectl -n envoy-gateway-system get svc -l gateway.envoyproxy.io/owning-gatewayclass=envoy-web -o name) 8443:8443
```

```bash
curl -sI --resolve gameplane.app.jyje.online:8443:127.0.0.1 https://gameplane.app.jyje.online:8443/
```

## First admin

The password must be at least 12 characters. Pipe it on stdin so it stays out of
the shell history:

```bash
printf '%s' "$ADMIN_PASSWORD" | kubectl -n gameplane-system exec -i deploy/gameplane-api -- \
  /api bootstrap-admin --username admin --password-stdin
```

## Verify a rollout

1. Argo CD synced the intended revision and the Application is `Healthy`.
2. The `gameplane-operator`, `gameplane-api` and `gameplane-web` Deployments are `Ready`.
3. The Certificate is `Ready`, the Gateway listener is `Programmed`, and the
   HTTPRoute is `Accepted`.
4. The dashboard answers through the port-forward and the admin can log in.
