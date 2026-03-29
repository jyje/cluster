# jyje/cluster

[![Dashboard](docs/assets/homer-dashboard.png)](https://app.jyje.online)

## Kubernetes Cluster v2
Second version of my Raspberry Pi cluster powered by MicroK8s.

Keywords: DevOps, MLOps, LLMOps, DevSecOps, MicroK8s

## Introduction
The first version was a private project, but it has lots of secrets and sensitive information.
So, I decided to create a new one from scratch and make it public.
The helm carts are moved to [**helm-charts**](https://github.com/jyje/helm-charts) repository.

## Architecture

![Architecture](docs/diagrams/hardware-architecture.png)

## LLMOps Architecture

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

## Maintainers
- [jyje](https://github.com/jyje)

## License
MIT
