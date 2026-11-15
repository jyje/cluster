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
and forwards plain HTTP to a dedicated `http-bridge` listener (port 8080) of the
Envoy proxy, through an `ExternalName` Service for `envoy-web` in
`envoy-gateway-system`. The hop stays inside the cluster, like the one from
ingress-nginx to every other app. The HTTPRoute then sends every path to
`gameplane-web`. Public traffic therefore already passes through Envoy
Gateway. At the cutover described in
[envoy-gateway-migration.md](../networks/envoy-gateway-migration.md), Envoy
takes the ports and the bridge Ingress, Service and listener are removed.

Two details of the bridge matter:

- ingress-nginx replaces some backend errors with its own error pages
  (`custom-http-errors`). The dashboard API answers 401 and 404 itself, and the
  SPA reads them, so the bridge Ingress overrides the list with an unused code.
- ingress-nginx ignores the `proxy-ssl-*` annotations unless `proxy-ssl-secret`
  is set, so it sends no SNI and the HTTPS listener of Envoy resets the
  connection. That is why the bridge uses the plain HTTP listener and not the
  HTTPS one. The HTTPS listener stays for the port-forward check and the final
  state.

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

## Single sign-on (authentik)

The dashboard signs in through authentik, next to the local admin account.

- The authentik side is the `authentik-gameplane-oidc` blueprint in
  [`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml). Gameplane needs a
  client secret, so the blueprint is sealed with the secret inside it. The same
  secret is sealed again as `gameplane-oidc` in the Gameplane Application.
- The application is bound to `AuthentikAdmin` only (see
  [authentik-access.md](authentik-access.md)), which also admits `ClusterAdmin`.
- Roles come from the `groups` claim: `AuthentikAdmin` and `ClusterAdmin` become
  dashboard admins. `defaultRole: deny` refuses anyone else.
- The redirect URL is the legacy path `/auth/oidc/callback`, which Gameplane
  keeps as an alias for this Helm-configured provider. The blueprint registers
  it and the `/auth/oidc/helm/callback` form.
- The local admin stays enabled as a break-glass login. Keep its password.

To rotate the client secret, generate a new one, seal it into both places and
sync both Applications. Check it as the owner: the login page shows an
"authentik" button, and signing in lands on the dashboard as an admin.
Troubleshooting follows [authentik-access.md](authentik-access.md). A sign-in
that answers `invalid_request` means the provider lost its `grant_types`.

## Guide: your first Factorio server in the web UI

This is a guide for creating a Factorio server in the dashboard. Nothing here is
in Git. The server is a `GameServer` that the operator reconciles, and it does
not touch the existing `factorio` Application. Check these points first,
because they are specific to this cluster.

**Before you start**

1. In **Admin Settings, General**, set **External URL** to
   `https://gameplane.app.jyje.online`. Share links and callbacks derive from it.
2. Do not reuse the existing server's address. The `factorio` Application owns
   UDP 34197 on its reserved address. A second server needs its own port.
3. Factorio uses UDP only. Players on a different client version cannot join,
   so match the client to the image version of the module.

**Create the server** (Servers, Create server, template **Factorio**)

1. **Name and password.** Set a game password. Leave it empty only for a test
   that nobody else can reach, because an empty password makes the server open.
   Keep **Public** off. `require_user_verification` is always on in this
   template, so every player needs a Factorio account.
2. **Placement.** Add the node selector `app.jyje.online/raspi.type: 5b`. The
   simulation is bound by one core, so run on a Pi 5 node, not a Pi 4. The module
   image is a multi-arch image and has an arm64 build.
3. **Resources.** The template asks for 1Gi and allows 4Gi and 2 CPUs. Lower the
   limits if the node is busy, the same way the existing server is sized.
4. **Storage.** 5Gi on the default StorageClass (NFS). Saves land there, so
   expect slower autosaves than on a local disk.
5. **Exposure.** This is the step to get right.
   - Do **not** choose `LoadBalancer` without `addressPool`. MetalLB's
     `default-addresspool` holds the node addresses, and handing a node address
     to a Service caused an ARP conflict before. `factorio-private` has one
     address and is reserved for the existing server.
   - For a first test choose **NodePort** and pin the port. Then forward WAN UDP
     on a spare port to that node port, or just join from the LAN with
     `<node address>:<node port>`.
   - Later, use a dedicated MetalLB pool with `addressPool`, or a relay tunnel
     (frp, Tailscale or playit.gg), which needs no router forward.
   If the expose choices do not show in the wizard, the operator has them off by
   default (see the networking notes in the Gameplane repository).
6. Leave **idle sleep** and **wake on connect** off for the first run.

**Check it**

1. The server reaches **Running** and the log shows the game hosting on UDP
   34197 inside the pod.
2. Join with the Factorio client by direct connect, using the address from the
   server's Overview. Make a recognizable change, wait for an autosave, restart
   the server from the dashboard and join again to see the change survived.
3. Take a backup only after you configure a backup target. None is configured
   here yet.

**Clean up**: deleting the server in the dashboard removes the pod and Service.
Check that its claim is gone too, so the NFS space is released.

## Verify a rollout

1. Argo CD synced the intended revision and the Application is `Healthy`.
2. The `gameplane-operator`, `gameplane-api` and `gameplane-web` Deployments are `Ready`.
3. The Certificate is `Ready`, the Gateway listener is `Programmed`, and the
   HTTPRoute is `Accepted`.
4. The dashboard answers through the port-forward and the admin can log in.
