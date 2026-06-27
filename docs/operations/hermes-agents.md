# Hermes Agents — GitOps Integration & Login

How the cluster runs **Hermes** AI agents (Discord-facing chat agents) under
ArgoCD, the two ways an agent authenticates to its model backend, and the
chart-native **OAuth device-flow login** that lets a Copilot agent mint its own
token at startup — no secret to seal.

The chart itself lives in a separate repo,
[`jyje/hermes-agent-helm`](https://github.com/jyje/hermes-agent-helm); this doc
covers how it is **consumed** by this cluster.

---

## Instances

Each agent is a separate ArgoCD `Application` (and a separate Discord bot) built
from the same chart. They differ only in source pinning, model backend, and how
they authenticate.

| App | Manifest | Chart source | Model / provider | Auth to model |
|-----|----------|--------------|------------------|---------------|
| `hermes-agent` | `clusters/r4spi/apps/hermes-agent.yaml` | **git** `jyje/hermes-agent-helm` @ `main`, path `charts/hermes-agent` | `litellm` → `openai/gpt-oss-120b` | LiteLLM proxy key (`OPENAI_API_KEY`, sealed) |
| `hermes-june`  | `clusters/r4spi/apps/hermes-june.yaml`  | **OCI** `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent` @ `0.5.1` | `litellm` → `openai/gpt-oss-120b` | LiteLLM proxy key (`OPENAI_API_KEY`, sealed) |
| `hermes-july`  | `clusters/r4spi/apps/hermes-july.yaml`  | **OCI** `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent` @ `0.5.1` | `copilot` → `gpt-4o` | **chart-native device-flow** (token on PVC, nothing sealed) |

All three are pinned to a Raspberry Pi 5b node
(`nodeSelector: app.jyje.online/raspi.type: 5b`) and deliver Discord bot
credentials via a `hermes-agent-creds` SealedSecret injected through the chart's
`extraResources`.

> **`hermes-agent` vs `hermes-june`** — same config, different source pin.
> `hermes-agent` tracks the chart's `main` branch (bleeding edge); `hermes-june`
> pins a signed OCI release. Prefer the OCI pattern for new agents.

---

## Two integration patterns

### A. LiteLLM-backed (`hermes-agent`, `hermes-june`)

The agent talks to the shared **LiteLLM proxy** as an OpenAI-compatible custom
provider. LiteLLM owns the upstream auth (NVIDIA NIM, OpenAI, etc.), so the agent
only needs the proxy key.

```yaml
config:
  providers:
    litellm:
      base_url: http://litellm.ollama-system.svc.cluster.local:4000/v1
      key_env: 'OPENAI_API_KEY'     # supplied by the sealed secret
      discover_models: true          # populate the picker from /v1/models
  model:
    provider: litellm
    default: openai/gpt-oss-120b      # must equal a LiteLLM model_name
```

The `openai/` prefix is the **LiteLLM `model_name`**, not a hermes vendor hint —
because `provider` is pinned to `litellm`, hermes routes the request through the
proxy rather than treating it as a built-in OpenAI vendor. The model_name must
match an entry in `clusters/r4spi/apps/litellm.yaml`.

**Sealed keys:** `OPENAI_API_KEY`, `OPENAI_BASE_URL`, plus the Discord trio
(`DISCORD_BOT_TOKEN`, `DISCORD_HOME_CHANNEL`, `DISCORD_ALLOWED_USERS`).

### B. Chart-native GitHub Copilot device-flow (`hermes-july`)

Hermes' built-in **Copilot** provider needs a `gho_`/`ghu_` OAuth token —
GitHub's Copilot API rejects PATs. Rather than seal a token (which would expire
and need rotation), the agent **mints its own** at startup via the chart's
`auth.deviceFlow` init container.

```yaml
config:
  model:
    provider: copilot
    default: gpt-4o
  auth:
    deviceFlow:
      enabled: true
      provider: github-copilot
      notify: discord            # deliver the verification prompt to Discord
```

**No Copilot token is sealed.** Only the Discord trio is sealed (reused to post
the verification prompt). See the next section for how the login works.

---

## Device-flow login (RFC 8628)

The `auth.deviceFlow` feature replaces the old one-off "copilot-login" Job with a
first-class init container on the agent Pod. Sequence on Pod start:

1. **seed-config** init copies `config.yaml` onto the PVC.
2. **auth-device-login** init runs the device grant:
   - If a usable token already exists on the PVC and `FORCE_RELOGIN=false`, it is
     validated and the flow is **skipped** (fast restarts — see below).
   - Otherwise it starts a GitHub **device authorization grant**, then posts the
     `verification_uri` + `user_code` to Discord (HTTP 200).
   - You approve on any device at <https://github.com/login/device>.
   - On success it writes `COPILOT_GITHUB_TOKEN` into `$HERMES_HOME/.env` on the
     PVC and `chown`s it to the agent uid (`10000:10000`).
3. The **hermes-agent** container starts and reads the token from `.env`.

```
auth-device-login  user_code=XXXX-XXXX  verify=https://github.com/login/device
auth-device-login  [discord] posted message (HTTP 200)
auth-device-login  AUTHORIZED. token_prefix=gho_ ... refresh_token=absent scope=read:user
auth-device-login  wrote COPILOT_GITHUB_TOKEN to /opt/data/.env (len=40)
```

### Token persistence & idempotent restarts

The token lives on the **PVC**, so it survives Pod restarts and rollouts. On the
next start, `token_is_valid()` re-checks it and **only an explicit `401`/`403`
forces a re-login** — `404`, network errors, and other statuses are treated as
"still valid" so a transient failure never blocks startup. In practice a healthy
agent restarts with:

```
auth-device-login  Existing COPILOT_GITHUB_TOKEN is present and valid - skipping device flow.
```

i.e. **no Discord re-prompt**. To force a fresh login, set
`config.auth.deviceFlow.forceRelogin: true` (or clear `.env` on the PVC).

---

## Chart distribution: OCI vs git

The chart is published two ways from `jyje/hermes-agent-helm`:

- **OCI** — `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent:<version>`,
  **cosign-signed** (keyless / Sigstore). This is what `hermes-june` and
  `hermes-july` consume. Verify a release:

  ```sh
  cosign verify ghcr.io/jyje/hermes-agent-helm/hermes-agent:0.5.1 \
    --certificate-identity-regexp 'https://github.com/jyje/hermes-agent-helm/.*' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com
  ```

- **Classic Helm repo** on GitHub Pages — `https://jyje.github.io/hermes-agent-helm`
  (the same artifacts indexed for `helm repo add`).

Releases are cut in the chart repo (`propose-release` → review PR → merge →
`release-chart` tags, publishes OCI, **signs**, and updates gh-pages). Bumping an
agent to a new chart version here is a one-line `targetRevision` change.

> The device-flow feature shipped in **0.5.x**; the signed pipeline was repaired
> in **0.5.1** (cosign now logs in to ghcr before signing).

---

## Deploying / upgrading an agent

1. Edit the agent's `Application` manifest (`targetRevision`, model, values).
2. Commit & push to `main` — the app-of-apps root reconciles it.
   (During this session apps were also `kubectl apply`'d directly to adopt
   already-running, manually-templated workloads.)
3. ArgoCD syncs; verify `Synced / Healthy`.

### Expect one Pod rollout on a chart-version bump

The chart stamps `helm.sh/chart: hermes-agent-<version>` into ConfigMap/Secret
labels, which feed the Deployment's `checksum/config` and `checksum/secret`
pod-template annotations. A version bump therefore changes those checksums and
triggers **one rollout** (`strategy: Recreate`). This is expected and safe:

- LiteLLM agents simply restart.
- Device-flow agents restart too, but the token on the PVC persists and the
  init **skips re-auth** (no Discord prompt).

Predict the change before applying:

```sh
helm template <name> oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent \
  --version <ver> -f <values> --no-hooks | sed -n '/^# Source/,$p' \
  | kubectl diff -n <ns> -f -
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Pod stuck in `Init` | `kubectl logs <pod> -c auth-device-login -n <ns>` — look for the device code / Discord post |
| Never got the Discord prompt | Verify the `hermes-agent-creds` SealedSecret decrypted (`kubectl get secret hermes-agent-creds -n <ns>`) and the bot can post to `DISCORD_HOME_CHANNEL` |
| Agent restarts re-prompt every time | Token isn't persisting — confirm the PVC is `Bound` and `$HERMES_HOME/.env` is `chown`ed to `10000:10000` |
| Wrong model / "model not found" | `default` must equal a LiteLLM `model_name` in `litellm.yaml` (LiteLLM agents) |
| Want a fresh Copilot token | Set `auth.deviceFlow.forceRelogin: true`, sync, approve the new prompt |

---

## Related

- Chart repo: <https://github.com/jyje/hermes-agent-helm>
- LiteLLM proxy & model catalog: `clusters/r4spi/apps/litellm.yaml`
- Sealed Secrets pattern: [introduction.md → Secrets](../introduction.md#secrets)
