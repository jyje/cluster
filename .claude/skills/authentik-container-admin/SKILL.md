---
name: authentik-container-admin
description: Safely administer Authentik running in Kubernetes or Docker containers, favoring declarative Blueprints, the Admin API, or the container management CLI over browser UI automation. Use when reading or changing Authentik configuration (providers, applications, flows, redirect URIs, scopes, grants) from a container/cluster environment.
---

# Authentik Container Admin

Authentik is frequently run in Kubernetes or Docker. When an agent needs to
inspect or change its configuration, the default instinct — driving the
browser admin UI — is the least safe, least inspectable option available.
This skill routes toward container-native and declarative mechanisms first,
and treats UI automation and live-database mutation as last resorts.

This skill is cluster-, provider-, and domain-agnostic. It never assumes a
specific namespace, workload name, hostname, or application. Discover those
from the user's environment before touching anything.

## Priority order

Always attempt these in order, and only fall through to the next one when
the current one is genuinely unavailable:

1. **Declarative Blueprint / GitOps source** — if the deployment manages
   Authentik config via `Blueprint` YAML/JSON checked into a repo (or an
   `authentik.blueprints` ConfigMap/volume), that file is the source of
   truth. Edit it there and let the normal apply/sync mechanism (`git push`
   + CD, Blueprint auto-discovery, Helm upgrade, etc.) roll it out. Do not
   make the same change directly against the running instance as well —
   that creates drift between the source of truth and reality.
2. **Authentik Admin API** — `https://<host>/api/v3/`, authenticated with a
   token. Read the target object first (`GET`), then send a minimal `PATCH`
   with only the changed field(s) — never a full `PUT` reconstructed from
   memory, which risks dropping fields you didn't intend to touch.
3. **Official container management command** — `ak` (the entrypoint script
   in the official image) or `manage.py` (Django management commands),
   invoked via `kubectl exec` / `docker exec` against the confirmed
   workload and container.
4. **Browser UI** — only when no programmatic path exists for the specific
   operation, or the user explicitly asks for the UI.

Never skip straight to the browser UI because it's familiar. If you find
yourself about to open a browser to change Authentik config, stop and check
whether steps 1–3 cover it first.

## Before any write

1. **Identify the target precisely.** Cluster/context, namespace, workload
   (Deployment/StatefulSet name), container name, and — for the Admin
   API — the exact object (provider/application/flow) by its `pk` or slug.
   Confirm these against the live environment (`kubectl config
   current-context`, `kubectl get pods -n <ns>`, etc.) rather than assuming
   names from a previous session or from a template.
2. **Read before writing.** Fetch and show the current value of every field
   you're about to change. Never construct a write from assumptions about
   what the current config "probably" looks like.
3. **Preserve unrelated configuration.** Redirect URIs, scopes, flows, and
   grants not part of the requested change must come back unchanged. When
   updating a list field (e.g. redirect URIs), append/modify in place —
   don't replace the whole list with only the new value.
4. **Make writes idempotent.** Re-running the same operation should reach
   the same end state without erroring or duplicating entries.

## Command discovery (required, don't guess)

Authentik's CLI surface and API fields vary across versions. Never assume a
subcommand, flag, or model field exists — confirm it first:

- Container entrypoint: `<exec-into-container> ak --help` and
  `ak help <subcommand>` for the specific subcommand you intend to use.
- Django management layer, when exposed: `manage.py help` and
  `manage.py help <command>`.
- Kubernetes: `kubectl exec <pod> -n <namespace> -c <container> -- ak --help`
  — confirm pod, namespace, and container name first with `kubectl get
  pods` / `kubectl describe pod`, don't guess a container name.
- `ak --help` and `ak help <subcommand>` boot the full Django app before
  printing anything — expect several seconds of JSON bootstrap log lines
  (config load, DB connection, app imports) first. That's normal startup
  noise, not a hang; the command list appears after it finishes booting.
- API/model fields: inspect the relevant Admin API schema or `OPTIONS`
  response read-only before writing (`GET /api/v3/schema/` or `OPTIONS` on
  the target endpoint). Some Authentik versions expose computed/friendly
  properties (e.g. a display name) that look writable but aren't — verify
  a field accepts writes before relying on it.

**Stop and report, don't guess or fall back to UI**, when the installed
version doesn't expose a documented safe write path for the requested
change. Tell the user what you found (version, available commands/fields)
and let them decide how to proceed.

## Secret handling

Never print, log, or persist:

- Client secrets, API tokens, or Authentik-issued secrets of any kind
- Authorization codes, access tokens, refresh tokens, or ID tokens
- Session cookies
- Encrypted values (even ciphertext) stored in the database
- Full sensitive configuration payloads (e.g. an entire provider object
  dumped with its secret field intact)

When a read-back or API response includes a secret field, redact it (e.g.
`client_secret: "<redacted>"`) before showing it to the user or including
it in any output. When you need to confirm a secret was set without
knowing its value, check for presence/non-emptiness or a hash/length, not
the value itself.

## Generic OIDC redirect URI update pattern

This pattern preserves existing configuration and works regardless of
provider or domain — substitute the real target's identifiers.

1. Identify the target OAuth2/OIDC provider by name or `pk` via the Admin
   API: `GET /api/v3/providers/oauth2/?name=<provider-name>`.
2. Read its current `redirect_uris` (or the equivalent field for the
   installed version — confirm the field name via the API schema, since it
   has changed across Authentik versions) in full.
3. Compute the new list by adding/removing only the specific URI(s)
   requested — keep every existing entry untouched.
4. `PATCH /api/v3/providers/oauth2/<pk>/` with just the updated field, not
   a full object replacement.
5. Read the object back and confirm the resulting list matches what was
   intended: the requested change applied, and every prior entry still
   present.

If a Blueprint manages this provider, make the same edit in the Blueprint
source instead of step 4, and skip the direct API write entirely.

## Live-database mutation

Treat direct writes to Authentik's PostgreSQL database as exceptional, not
a normal fallback. Only do this when:

- No declarative source (Blueprint) exists for the object, **and**
- The Admin API and management CLI genuinely don't expose a way to make
  the change, **and**
- The user has explicitly authorized the exact target (table, row, field)
  after being told this is a direct database mutation.

Never touch encrypted columns, session tables, or token tables directly.
A live-database mutation still requires read-before-write and a
minimal-diff update — same discipline as the API path.

## Verification

After any change:

- Do a **minimal read-back** of the changed object via the same mechanism
  used to write it (Blueprint diff, API `GET`, or `manage.py shell`
  read-only query) and confirm only the intended field(s) differ from
  before.
- Where appropriate, verify with a **non-authenticating request** — e.g.
  confirm a redirect URI is recognized via the provider's metadata/config
  endpoint, or check the OIDC discovery document. Do not complete an
  actual user login, and do not expose redirect query values (`code`,
  `state`, tokens) merely to prove a redirect URI works — a config-level
  check is sufficient.

## Scope

This skill covers reading and changing Authentik configuration in
container/cluster environments. It does not cover initial Authentik
installation, unrelated Kubernetes cluster administration, or general
OIDC client-side integration work outside of Authentik's own config.
