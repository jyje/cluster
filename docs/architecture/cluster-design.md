# Cluster Design

The macro-level design of this cluster: the **layers** a change passes through to
reach a running workload, the **logical stack** those workloads form, and the
**design decisions** (with their failure modes) that shape both.

For the repository tour — directory layout, commit convention, secrets — see
[introduction.md](../introduction.md). This document is the *why* behind the *what*.

---

## Delivery Layers

Everything is reconciled by ArgoCD from `main`. A change ripples downward through
five layers; nothing is applied by hand in steady state.

```
L0  Bootstrap            ArgoCD itself (the only thing installed out-of-band)
        │
L1  Root app-of-apps     clusters/r4spi/apps.yaml
        │                  ├─ AppProject "base"  (what the apps may touch)
        │                  └─ Application "apps"  (recurse: clusters/r4spi/apps/)
        │
L2  Per-app Applications clusters/r4spi/apps/*.yaml   (one file = one Application)
        │
L3  Vendored Helm charts helm/<group>/<chart>-<version>/   (never pulled at deploy)
        │
L4  extraResources       inline manifests in each Application's valuesObject
                           (SealedSecrets, ClusterIssuers, CNPG clusters, …)

  ┌ side channel ─────────────────────────────────────────────────────────┐
  │ manifests/   Raw Kubernetes manifests not driven by Helm (e.g. MetalLB │
  │              IPAddressPool / L2Advertisement).                          │
  └────────────────────────────────────────────────────────────────────────┘
```

| Layer | Lives in | Owns | Reconciled by |
|-------|----------|------|---------------|
| L0 Bootstrap | out-of-band install | ArgoCD control plane | manual (once) |
| L1 Root app-of-apps | `clusters/r4spi/apps.yaml` | `AppProject base` + recursive `Application apps` | ArgoCD self-manages |
| L2 Applications | `clusters/r4spi/apps/*.yaml` | one workload each, pinned to an L3 chart | L1 (auto-sync) |
| L3 Helm charts | `helm/<group>/<chart>-<ver>/` | vendored, version-pinned templates | L2 references by `path` |
| L4 extraResources | `valuesObject.extraResources` | trust + secrets + DB clusters, rendered with `tpl` | L3 chart template |
| Side: raw manifests | `manifests/` | infra primitives outside Helm | applied alongside |

**Why this shape:** the root app **recurses** one directory, so adding a workload
is a single new file — no central registry to edit. Charts are **vendored**, not
pulled, so a deploy is reproducible from git alone and an upgrade is a visible
directory swap. `extraResources` keeps an app's trust (ClusterIssuers), secrets
(SealedSecrets) and data (CNPG clusters) **in the same Application** as the
workload, rather than scattered across loose manifests.

---

## Logical Stack

What those Applications compose into, bottom-up:

| Layer | Components | Notes |
|-------|-----------|-------|
| **Edge / Ingress** | ingress-nginx, MetalLB (L2) | ingress is a hostNetwork DaemonSet — see [Decisions](#design-decisions) |
| **Certificates** | cert-manager + Let's Encrypt (HTTP-01) | ClusterIssuers delivered as L4 extraResources |
| **Service Mesh** | Istio Ambient | *evaluation / temporarily disabled* |
| **Storage** | Longhorn (block), SeaweedFS (object), NFS (legacy) | hybrid governance |
| **Stateful data** | CloudNativePG, Qdrant | Postgres for metadata, vectors for RAG |
| **LLMOps** | LiteLLM proxy → NIM / Ollama / OpenAI, Open WebUI | multi-backend gateway |
| **Agents** | Hermes (Discord) | see [hermes-agents.md](../operations/hermes-agents.md) |
| **Observability** | LGTM stack, metrics-server | full-stack telemetry |
| **Secrets** | Sealed Secrets, Infisical | encrypted-at-rest, public-safe repo |
| **GitOps** | ArgoCD | reconciles every layer above |

---

## Design Decisions

The decisions that were not obvious — each one earned by an outage or a dead end.

### Direct ingress, no tunnel

The cluster previously fronted everything through a **Cloudflare Tunnel** (no
public IP exposed). That was removed in favour of **direct ingress**: the home
router port-forwards `:80/:443` to the nodes, and NGINX terminates there.

**Trade-off:** the tunnel hid the origin and needed no inbound ports, but added a
hop, an external dependency, and an opaque failure surface. Direct ingress is
fewer moving parts and keeps TLS issuance (HTTP-01) self-contained — at the cost
of exposing the router's ports and trusting MetalLB/ingress to behave (see next).

### Ingress is a hostNetwork DaemonSet, never a LoadBalancer

**The MetalLB L2 address pool overlaps the nodes' own addresses.** If the ingress
controller is exposed as `type: LoadBalancer`, MetalLB hands it a VIP that a node
**already owns**, and now two machines answer ARP for the same address. The L2
conflict is not contained to ingress: it corrupts the affected node's
**kubelet ↔ API server** path, which then cascades —

> *Observed cascade:* a node goes `NotReady` → CloudNativePG instance managers
> can't refresh their TLS secret from the API server → Postgres clusters lose
> their primary and their `-rw` endpoint empties → every app behind those DBs
> (dashboards, the LLM UI) returns 5xx. The root cause was **layer-2**, three
> layers down from the symptom.

**Resolution / standing rule:** run ingress as a **hostNetwork DaemonSet**
(`hostNetwork: true`, `dnsPolicy: ClusterFirstWithHostNet`, `service.type: ClusterIP`)
so each node binds `:80/:443` directly and **no VIP is needed**. This also matches
the old MicroK8s ingress addon and removes a hop. Keep MetalLB strictly for
workloads whose addresses do **not** collide with the nodes.

### Declarative certificate trust

The whole certificate chain is reproducible from git. `ClusterIssuer`s are not
`kubectl apply`'d by hand — they ride along as **L4 extraResources** on the
cert-manager Application, so the trust anchors version with the operator that
consumes them. cert-manager then issues Let's Encrypt certs via the HTTP-01
challenge through the NGINX ingress above.

### Prune with scope, never with the app-of-apps

Auto-sync does **not** prune by default, so structural migrations leave orphans —
moving a controller between namespaces, or flipping a workload between Deployment
and DaemonSet, strands the old objects. Prune them **per-Application**
(`argocd app sync <app> --prune`, or a scoped sync), **never** by pruning the
recursive root app — a blanket prune would tear down unrelated workloads across
the whole cluster.

---

## Related

- [introduction.md](../introduction.md) — repository tour, conventions, secrets
- [operations/hermes-agents.md](../operations/hermes-agents.md) — agent integration
- [operations/litellm-startup-probe-tuning.md](../operations/litellm-startup-probe-tuning.md) — ARM64 probe tuning
