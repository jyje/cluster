# Hermes dashboard behind authentik

[한국어](hermes-dashboard-ko.md)

How a Hermes agent exposes its management dashboard in this cluster, and how
users sign in. The dashboard is off by default: `hermes gateway run` is an
outbound-only messenger and has no web UI. For the agents themselves see
[hermes-agents.md](hermes-agents.md).

| File | What it is |
| --- | --- |
| [`examples/hermes-dashboard-application.yaml`](examples/hermes-dashboard-application.yaml) | A complete Argo CD Application with the dashboard on. Copy it and rename "example". |
| [`examples/hermes-dashboard-blueprint.yaml`](examples/hermes-dashboard-blueprint.yaml) | The matching authentik blueprint (provider, application, group binding). |

The live instance is `hermes-agent-henry`
([`clusters/r4spi/apps/hermes-agent-henry.yaml`](../../clusters/r4spi/apps/hermes-agent-henry.yaml)),
and its blueprint is `authentik-hermes-dashboard` in
[`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml).

## Treat sign-in as shell access

The dashboard shows API keys, and a signed-in user can create shell hooks and
use the Chat tab. Whoever may sign in can effectively run commands in the pod.
Upstream has no user allowlist of its own, so **the only access control is the
group binding on the authentik application.** Keep it to `AuthentikAdmin`
(which also admits `ClusterAdmin` through the group hierarchy) unless there is
a reason to widen it.

Upstream also fails closed: on any non-loopback bind the dashboard refuses to
start without an auth provider. `--insecure` and `HERMES_DASHBOARD_INSECURE`
are deprecated no-ops and do not turn the gate off.

## How it fits together

```
browser ──https──> ingress-nginx ──> Service :9119 ──> hermes dashboard (s6 service)
   │                                                   same pod as `gateway run`
   └── sign-in redirect ──> authentik (public PKCE client, no secret)
```

- The dashboard is an s6 service inside the image, switched on by
  `dashboard.enabled`, which renders `HERMES_DASHBOARD=1`. Prefer it over a bare
  `HERMES_DASHBOARD` in `env`: only the chart value brings the readiness probe,
  the derived `public_url` and `trusted_proxies`, and the auth-provider check.
- Hermes registers in authentik as a **public** client with PKCE. There is no
  client secret, so the blueprint is a plain ConfigMap and nothing is sealed.
  The issuer and client id are not secrets either.
- The chart renders everything from `values`, so no chart change is needed. It
  is available in chart 1.21.0, the version these examples use.

## Values that matter

| Value | Why |
| --- | --- |
| `dashboard.enabled: true` | Starts the dashboard and adds a TCP readiness probe, so the Ingress does not answer 502 while it starts. |
| `dashboard.auth.provider: oidc` | The chart fails to render when the issuer or client id is missing, instead of leaving an Ingress that answers 503. |
| `config.dashboard.oauth.self_hosted.issuer` | `https://authentik.app.jyje.online/application/o/<slug>/`. The slug is the authentik application slug. |
| `config.dashboard.oauth.self_hosted.client_id` | Must equal the provider's `client_id` in the blueprint. |
| `dashboard.trustedProxies` | Networks allowed to send `X-Forwarded-*`. ingress-nginx runs on the host network of several nodes, so list the node network **and** the pod network (`10.0.4.0/24` and `10.1.0.0/16` here). With only one of them the session cookies lose `Secure` depending on the node a request enters through, and nothing warns you. |
| `service.enabled: true` and `ingress` | The chart does not expose a listener by itself. |
| `ingress.hosts[0].host` and `tls` | `public_url` is derived from the first host (https once `tls` is set). It must equal the redirect URI registered in authentik, apart from the `/auth/callback` suffix. |

Homer finds the card through the Ingress annotations. The chart stamps
`app.kubernetes.io/name: hermes-agent` on every instance, so one entry in the
Homer `ingressSelector` covers all of them. Leave out the Ping `type`: the page
sits behind a sign-in.

## Rollout order

1. **DNS**: add a CNAME for `<host>` to the same target the other
   `*.app.jyje.online` records use. The certificate is issued with HTTP-01, so
   the name has to resolve first. There is no wildcard record.
2. **Merge** the change. Argo CD syncs the agent. The authentik worker applies a
   changed blueprint within minutes, and a brand new blueprint file can wait for
   the hourly discovery task (see [authentik-access.md](authentik-access.md)).
3. **Check authentik**: the blueprint instance must report success, and the
   application and provider must exist. A missing flow slug or signing key only
   fails this blueprint; authentik keeps running.
4. **Check the agent**: the pod becomes Ready once port 9119 listens. The first
   start can take minutes while bundled skills sync onto the volume, longer on
   network storage.
5. **Check sign-in** (below).
6. **Follow-up change**: set `bootstrap.overwrite` back to `false`.

### Why `bootstrap.overwrite` is one-shot

`public_url`, `trusted_proxies` and the OIDC issuer are written into
`config.yaml` only when the volume is first seeded, and `bootstrap.overwrite`
defaults to `false`. A later sync that changes the host or any `dashboard.*`
value therefore does not reach the pod, and a stale `public_url` breaks the
sign-in callback. Set `bootstrap.overwrite: true` for the sync that changes
them. It replaces `config.yaml` (and a configured `SOUL.md`) with the rendered
content, so edits the agent made at runtime are lost. Take a copy first if they
matter, and set it back to `false` in the next change. Left on, every sync
replaces the file again.

## Verify

Without a session, `GET /` redirects to the sign-in page, and `/api/env` and
`/api/config` answer 401. After signing in as a member of the bound group,
`GET /api/auth/me` reports the provider, and the session cookies are
`__Host-`, `Secure` and `HttpOnly`. Also check, in the browser:

- the session cookie is marked `Secure` (a missing flag means
  `trustedProxies` does not match the address the dashboard sees);
- a user outside the bound group is stopped by authentik and never reaches the
  dashboard.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `GET /auth/login` answers 503 | The issuer is wrong. The dashboard's own body names the reason (for example "OIDC discovery returned 404"), but a proxy with custom error pages can replace it with a generic 503, so read it from the Service directly. A trailing slash difference is tolerated. |
| authentik shows "Permission denied" right after a successful sign-in | The account is not in a group bound to the application. The dashboard is bound to `AuthentikAdmin`, which the owner is always in; see [authentik-access.md](authentik-access.md) for the rule and the fix. |
| Sign-in comes back to `/auth/callback` with `error=invalid_request` ("The request is otherwise malformed") | The provider allows no grant type. A provider created from a blueprint has an empty `grant_types` unless the blueprint sets it. The authentik server log says `Invalid grant_type for provider`. Add `grant_types: [authorization_code, refresh_token]` to the provider. |
| authentik shows "Unregistered redirect_uri" | The redirect URI in the blueprint does not equal `public_url` + `/auth/callback`. Common after changing the host. |
| The callback fails after a host change | `public_url` in `config.yaml` is stale. Sync once with `bootstrap.overwrite: true`. |
| 502 from the Ingress right after rollout | The pod is still starting (skills sync). Wait for Ready; the readiness probe keeps the Ingress off it until then. |
| The pod never gets Ready | No auth provider, so the dashboard failed closed. Check the issuer, the client id and `dashboard.auth.provider`. |
| Cookies not `Secure` | `trustedProxies` misses the node network or the pod network. List both. |
| The Ingress times out after enabling `networkPolicy` | The policy denies all inbound traffic and a host-network controller is not matched by pod or namespace selectors. Allow port 9119 in `networkPolicy.extraIngress` for both the node network and the pod network. The chart ships [`values-networkpolicy-dashboard.yaml`](../../helm/hermes-agent/hermes-agent-1.21.0/values-networkpolicy-dashboard.yaml) as a measured example. Not enabled for henry today. |
| No Homer card | `hermes-agent` is missing from the Homer `ingressSelector`, or the Ingress has no Homer annotations. |
| The blueprint did not apply | A default flow slug or the self-signed key pair is named differently here. Fix the names in the blueprint; the other blueprints are not affected. |

## Add a dashboard to another agent

1. Copy the two example files and rename "example" everywhere. Keep the host,
   the issuer slug, the client id and the redirect URI consistent.
2. Add the blueprint ConfigMap to `authentik.yaml` under `additionalObjects`
   and list it under `blueprints.configMaps`.
3. Create the DNS record (rollout step 1).
4. The Homer `ingressSelector` already includes `hermes-agent`.
5. Follow the rollout order above. A brand new instance does not need
   `bootstrap.overwrite` (its volume is seeded with these values on the first
   start), so the example keeps it commented out. Only an agent that already has
   a volume needs it, together with the follow-up that clears it.
