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

### 3. LLMOps Architecture
```mermaid
graph TD
    subgraph UI_Layer [User Interface]
        OWUI["Open WebUI (Pod)"]
    end

    subgraph LLM_Orchestration [AI Infrastructure]
        LiteLLM["LiteLLM Proxy (Pod)"]
    end

    subgraph Storage [State & Vectors]
        subgraph Persistence
            CNPG["CloudNativePG (Cluster)"]
            Qdrant["Qdrant (Vector DB)"]
        end
    end

    subgraph LLM_Backends [Inference Services]
        NIM["NVIDIA NIM (External)"]
        Ollama["Ollama (Local Pod)"]
        OpenAI["OpenAI (External)"]
    end

    %% Flow Relationships
    User((User)) --> OWUI
    OWUI -- "LLM Request (v1)" --> LiteLLM
    OWUI -- "Query/Store Documents" --> Qdrant

    LiteLLM -- "Proxy / Routing" --> NIM
    LiteLLM -- "Proxy / Routing" --> Ollama
    LiteLLM -- "Proxy / Routing" --> OpenAI
    LiteLLM -- "Sync Metadata" --> CNPG

    %% Styling
    style User fill:#333,color:#fff
    style OWUI fill:#3b82f6,color:#fff,stroke:#1d4ed8
    style LiteLLM fill:#ef4444,color:#fff,stroke:#b91c1c
    style Qdrant fill:#10b981,color:#fff,stroke:#047857
    style CNPG fill:#8b5cf6,color:#fff,stroke:#6d28d9
    style NIM fill:#84cc16,color:#fff,stroke:#4d7c0f
    style Ollama fill:#f59e0b,color:#fff,stroke:#b45309
```

### 4. GitOps & Secrets
- **Continuous Delivery**: [ArgoCD](https://argoproj.github.io/cd/)
- **Secrets**: Sealed Secrets & [Infisical](https://infisical.com/)

### 5. Storage Strategy
- **Object Storage**: [SeaweedFS](https://github.com/seaweedfs/seaweedfs) (S3-compatible)
- **Distributed Block**: [Longhorn](https://longhorn.io/)
- **Legacy Storage**: NFS Subdir External Provisioner

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
