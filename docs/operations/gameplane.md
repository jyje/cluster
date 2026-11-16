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

The public host is `gameplane.app.jyje.online`. The Ingress and the Certificate
live in the Application (`extraResources`), and the Ingress uses the `higress`
class. Higress sends every path straight to `gameplane-web`, which serves the
dashboard and proxies the API. The Certificate is an explicit one next to the
secret that the Ingress uses (its name `gameplane-envoy` is historical).

Three details of the Ingress matter:

- The dashboard API answers 401 and 404 itself, and the SPA reads them. Higress
  passes backend errors through unchanged, so nothing has to switch off a
  global error page, which the old controller needed.
- The request rate cap is `higress.io/route-limit-rps`, which is per route and
  not per client. There is no body size cap and no connection cap. Uploads,
  WebSocket and SSE are covered by the gateway-wide idle timeout of one hour.
- The Homer card pings `/healthz` from the browser, so the Ingress allows CORS
  for the dashboard origin only.

The DNS record is a CNAME to the same DDNS host as the other `app.jyje.online`
names. The Let's Encrypt HTTP-01 challenge needs it before the Certificate can
be issued.

The Homer card is a manual entry in the `3. Management` group of `homer-instance`,
not an Ingress annotation.

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

## Guide: a game server behind the UDP Gateway

Game servers are created in the dashboard. A server is a `GameServer` that the
operator reconciles, so nothing about the server itself is in Git. Public UDP
reaches it through the `games` Gateway, which is in Git (see
[envoy-udp-gateway.md](envoy-udp-gateway.md)). Points that are specific to this
cluster:

1. In **Admin Settings, General**, set **External URL** to
   `https://gameplane.app.jyje.online`. Share links and callbacks derive from it.
2. **Pin the image.** Pick the version in the wizard, then set the image by tag
   and digest in the server settings (`spec.image`). A floating tag or channel
   changes the game version under you, and clients on another version cannot
   join. Check that the image has a native arm64 build: an image that only
   ships an x86 binary runs through an emulator and is much slower.
3. **Placement.** Add the node selector `app.jyje.online/raspi.type: 5b`. The
   simulation is bound by one core, so use a Pi 5 node, not a Pi 4.
4. **Name.** The public route sends traffic to the Service that has the
   server's name (`world-1` in `manifests/envoy-gateways/games-route.yaml`).
   Create the server under that name, or change the route.
5. **Exposure.** Leave it at `ClusterIP`. Public UDP comes in through the
   Gateway. Do **not** choose `LoadBalancer` without a dedicated address pool:
   MetalLB's `default-addresspool` holds the node addresses, and handing a node
   address to a Service caused an ARP conflict before.
6. Leave **idle sleep** and **wake on connect** off for the first run.
7. Set a game password, and keep the server unlisted.

**Check it**

1. The server reaches **Running** and the log shows the game hosting on its
   UDP port inside the pod.
2. Join from a client by direct connect with the public name and the game port.
   Make a recognizable change, wait for an autosave, restart the server from the
   dashboard and join again to see the change survived.
3. Take a backup only after you configure a backup target. None is configured
   here yet.

**Moving an existing world in**: stop the server, copy the save into the data
volume's saves directory (the dashboard Files tab, or `kubectl exec` with a
pipe), start it, and check the log for the loaded save. The server version must
be the same as or newer than the one that wrote the save, and every mod in the
save has to be present on the server.

**Clean up**: deleting the server in the dashboard removes the pod and Service.
Check that its claim is gone too, so the NFS space is released.

## A game stays at Starting with AgentStale

The agent sidecar of each game reports its status through the Kubernetes API.
Gameplane's default policies allow it to reach the API server only on TCP 443
and 6443, but MicroK8s serves the API on 16443, and Calico checks the policy
after the Service address is translated to the endpoint. The heartbeat then
times out (`dial tcp 10.152.183.1:443: i/o timeout` in the agent log), and the
server shows `Starting` with `AgentStale` although the game itself runs. The
`allow-agent-to-microk8s-apiserver` policy in the Application opens 16443 for
game and sentinel pods. If you see the symptom again, compare the endpoint port
of `kubectl get endpoints kubernetes` with the policy.

The game log also shows a line such as `New RCON connection from <node address>`
every 10 seconds. These come from the kubelet probes, which check the RCON port,
and are harmless.

## Verify a rollout

1. Argo CD synced the intended revision and the Application is `Healthy`.
2. The `gameplane-operator`, `gameplane-api` and `gameplane-web` Deployments are `Ready`.
3. The Certificate is `Ready`, the Gateway listener is `Programmed`, and the
   HTTPRoute is `Accepted`.
4. The dashboard answers through the port-forward and the admin can log in.
