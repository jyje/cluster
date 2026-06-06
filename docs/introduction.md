# Cluster Introduction

A tour of this repository for first-time visitors — what it does, how it is
organized, and the conventions that keep it maintainable.

---

## What This Repo Is

This is a **GitOps-managed Kubernetes cluster** running on low-power ARM64
hardware (Raspberry Pi 4/5). Every resource — applications, infrastructure,
secrets — is declared in this repository and reconciled automatically by ArgoCD.

The cluster deliberately uses enterprise-grade tooling (service mesh, distributed
storage, LLM proxy, vector DB) to prove that production patterns scale *down*
to constrained hardware, not just up.

**Design principles:**
- **Declarative Everything** — if it runs on the cluster, it lives in this repo
- **Public-safe by default** — secrets are encrypted before commit (Sealed Secrets)
- **ARM64 first** — every component is validated on AARCH64 before being added
- **Vendor Helm charts** — all charts are vendored locally for reproducibility

---

## Repository Structure

```
cluster/
├── clusters/
│   └── r4spi/
│       ├── apps/          # ArgoCD Application manifests (one file per app)
│       └── infra/         # Infrastructure-level ArgoCD Applications
├── helm/
│   └── <app>/
│       └── <chart>-<version>/   # Vendored Helm charts (never pulled at deploy time)
├── manifests/             # Raw Kubernetes manifests not managed by Helm
├── docs/
│   ├── diagrams/          # Architecture diagrams
│   ├── migrations/        # Step-by-step data migration guides
│   ├── networks/          # Networking setup guides
│   └── operations/        # Operational tuning notes and runbooks
└── scripts/               # Cluster utility scripts (validation, monitoring)
```

### `clusters/r4spi/apps/`

Each file is an ArgoCD `Application` manifest. It points to a vendored chart
under `helm/` and overrides values via `spec.source.helm.valuesObject`.

Pattern:
```yaml
spec:
  source:
    path: helm/<app>/<chart>-<version>
    helm:
      valuesObject:
        # all overrides live here — no separate values file needed
```

### `helm/`

Charts are vendored at a specific version. Directory naming convention:
```
helm/<group>/<chart-name>-<version>/
```

When upgrading, the old versioned directory is removed and a new one is added —
git history shows exactly what changed between versions.

### `extraResources` pattern

All vendored charts are patched to support an `extraResources` field, which lets
the ArgoCD Application manifest inject additional Kubernetes resources (e.g.
SealedSecrets, CloudNativePG clusters) without needing a separate manifest file.

Resources in `extraResources` support Helm template syntax (`{{ .Release.Namespace }}`
etc.) via `tpl` rendering.

---

## Commit Convention

All commits follow **Gitmoji + Conventional Commits**:

```
<emoji> <type>(<domain>): <title>

<optional body>
```

| Emoji | Type | When |
|-------|------|------|
| ✨ | `feat` | New application or feature |
| 🛠️ | `fix` | Intentional config change |
| 🐛 | `bug` | Bug fix |
| ⬆️ | `dep` | Dependency / chart upgrade |
| ♻️ | `refactor` | Restructuring without behavior change |
| 🗑️ | `remove` | Removing an app or resource |
| 🔐 | `security` | Secrets / RBAC changes |
| 📄 | `docs` | Documentation |
| 🔧 | `chore` | Maintenance |

Domain examples: `(litellm)`, `(open-webui)`, `(helm)`, `(istio)`

---

## GitOps Workflow

1. **Edit** — change an ArgoCD Application manifest or vendored chart value
2. **Commit & push** to `main`
3. **ArgoCD** detects the change and syncs the cluster (auto-sync or manual)
4. No `kubectl apply` by hand — the cluster state always reflects the repo

### Secrets

Secrets are encrypted with **Sealed Secrets** before being committed. The
encrypted blobs are safe to store in a public repo. The controller on the cluster
holds the private key and decrypts at runtime.

Pattern inside `extraResources`:
```yaml
extraResources:
  - apiVersion: bitnami.com/v1alpha1
    kind: SealedSecret
    metadata:
      name: my-app-creds
    spec:
      encryptedData:
        some-key: <encrypted-blob>
```

---

## AI / LLMOps Stack

The cluster runs a multi-backend LLM gateway:

```
User → Open WebUI → LiteLLM Proxy → NVIDIA NIM (external)
                                  → Ollama       (local)
                                  → OpenAI       (external)
              └──────────────────── Qdrant (vector DB)
                                    CloudNativePG (metadata)
```

**LiteLLM** (`clusters/r4spi/apps/litellm.yaml`) is the central proxy. Models
are declared in `proxy_config.model_list` organized into three sections:
`# Text Models`, `# Image Models`, `# Embedding Models`.

---

## Operations Notes

Runbooks and tuning notes live under `docs/operations/`. Current entries:

| Document | Topic |
|----------|-------|
| [litellm-startup-probe-tuning.md](operations/litellm-startup-probe-tuning.md) | Startup probe tuning for slow ARM64 nodes |

---

## Key Technologies

| Layer | Technology |
|-------|-----------|
| Orchestration | [MicroK8s](https://microk8s.io/) |
| GitOps | [ArgoCD](https://argo-cd.readthedocs.io/) |
| Service Mesh | [Istio Ambient](https://istio.io/latest/docs/ambient/) *(evaluation)* |
| Ingress | NGINX Ingress Controller |
| Load Balancer | MetalLB (L2) |
| Distributed Block | [Longhorn](https://longhorn.io/) |
| Object Storage | [SeaweedFS](https://github.com/seaweedfs/seaweedfs) |
| Secrets | [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) |
| LLM Proxy | [LiteLLM](https://github.com/BerriAI/litellm) |
| LLM UI | [Open WebUI](https://github.com/open-webui/open-webui) |
| Vector DB | [Qdrant](https://qdrant.tech/) |
| DB Operator | [CloudNativePG](https://cloudnative-pg.io/) |
| TLS | cert-manager + Cloudflare DNS |
| Tunnel | Cloudflare Tunnel (no public IP exposure) |
