# jyje/cluster

[![Dashboard](docs/assets/homer-dashboard.png)](https://app.jyje.online)

## Kubernetes Cluster v2
Second version of my Raspberry Pi cluster powered by MicroK8s.
Keywords: **DevOps**, **MLOps**, **LLMOps**, **GitOps**, **Service Mesh**, **MicroK8s**

This is a self-hosted, sovereign Kubernetes cluster built on Raspberry Pi hardware. It represents a "Production-grade HomeLab" where enterprise-level technologies are implemented in a resource-constrained environment.

This v2 cluster focuses on **Declarative Everything**, **Flexible AI Serving**, and **Hybrid Storage Governance**.

> [!NOTE]
> Service Mesh (Istio Ambient) is currently in evaluation and temporarily disabled for resource optimization.

## Technical Architecture

### Overview
Infra, network edge, AI workload, and the GitOps loop that reconciles all of it — in one landscape view. Each section below drills into one column.

![System Overview](docs/diagrams/system-overview.svg)

### 1. Hardware Stack
![Architecture](docs/diagrams/hardware-architecture.png)

- **Platform**: 4x Raspberry Pi 4/5 (8GB RAM each)
- **Orchestration**: [MicroK8s](https://microk8s.io/)
- **OS**: Debian GNU/Linux 12 (bookworm)

### 2. Networking & Service Mesh
- **Service Mesh**: **Istio Ambient Mesh** (Evaluation / Temporarily disabled)
- **Ingress**: NGINX Ingress Controller, run as a **hostNetwork DaemonSet** so each node binds `:80/:443` directly (no extra L2 hop, mirrors the old MicroK8s addon).
- **Load Balancer**: MetalLB (L2 mode) — reserved for workloads that do not collide with node addresses (see [Design & Insights](#design--insights)).
- **Certs**: Cert-manager issuing Let's Encrypt certificates via the ACME **HTTP-01** challenge through the NGINX ingress. `ClusterIssuer` definitions are themselves managed declaratively by ArgoCD.

### 3. Logical Architecture
The full logical stack — edge, certificates, service mesh, storage, stateful data, LLMOps, agents, observability, secrets, and GitOps — grouped the way an AWS reference architecture diagram groups services, but every icon is the component's own real logo.

![Logical Architecture](docs/diagrams/logical-architecture.svg)

### 4. GitOps & Secrets
- **Continuous Delivery**: [ArgoCD](https://argoproj.github.io/cd/)
- **Secrets**: Sealed Secrets & [Infisical](https://infisical.com/)

Every change is reconciled through five delivery layers (L0 bootstrap → L1 root app-of-apps → L2 per-app Applications → L3 vendored Helm charts → L4 extraResources) — see [Design & Insights](#design--insights) for the full rationale.

![Delivery Pipeline](docs/diagrams/delivery-pipeline.png)

### 5. Storage Strategy
- **Object Storage**: [SeaweedFS](https://github.com/seaweedfs/seaweedfs) (S3-compatible)
- **Distributed Block**: [Longhorn](https://longhorn.io/)
- **Legacy Storage**: NFS Subdir External Provisioner

> [!NOTE]
> Hardware Stack and Delivery Pipeline are generated from [docs/diagrams/r4spi.ipynb](docs/diagrams/r4spi.ipynb). Overview and Logical Architecture are hand-laid-out [draw.io](https://www.diagrams.net/) files ([system-overview.drawio](docs/diagrams/system-overview.drawio), [logical-architecture.drawio](docs/diagrams/logical-architecture.drawio)) — Graphviz's automatic layout couldn't give these two the tight, centered placement they needed. Icons are each project's own official logo — sourced from the [`diagrams`](https://diagrams.mingrammer.com/) package, [lobehub/lobe-icons](https://github.com/lobehub/lobe-icons) (MIT), and each project's own brand assets.

## Key Features
- **ARM64 Optimized**: All components are tailored for AARCH64.
- **Hybrid Storage**: Combining high-performance block storage with scalable object storage (SeaweedFS).
- **Flexible AI**: Integrated with NVIDIA NIM for high-performance inference, with future plans for **Private LLM** infrastructure (e.g., NVIDIA DGX Spark).
- **Conversational Agents**: Discord-facing [Hermes](https://github.com/jyje/hermes-agent-helm) agents, with a chart-native OAuth **device-flow login** that mints a GitHub Copilot token at startup — no secret to seal ([docs](docs/operations/hermes-agents.md)).
- **Observability**: LGTM Stack (Loki, Grafana, Tempo, Mimir) for full-stack monitoring.

## Design & Insights

The macro-level design — the **delivery layers** a change passes through, the
**logical stack** of workloads, and the **design decisions** behind them — is
documented in **[docs/architecture/cluster-design.md](docs/architecture/cluster-design.md)**.

Highlights:
- **Direct ingress, no tunnel** — the Cloudflare Tunnel was retired for direct, router-forwarded ingress.
- **Ingress as a hostNetwork DaemonSet, never a LoadBalancer** — the MetalLB pool overlaps node addresses, so a VIP would trigger an L2/ARP conflict that cascades into the API server and stateful workloads.
- **Declarative certificate trust** — `ClusterIssuer`s ride along as Helm `extraResources`, reproducible from git.
- **Scoped pruning** — migrations are pruned per-Application, never via the recursive root app.

## Maintainers
- [jyje](https://github.com/jyje)

## License
MIT
