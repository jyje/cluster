# Cloudflare Tunnel

## Overview

Replace direct DDNS exposure with a Cloudflare Tunnel to hide the home public IP and eliminate inbound port forwarding requirements.

| Item | Value |
|------|-------|
| Date | 2026-05-10 |
| Tunnel name | (managed via Cloudflare Zero Trust dashboard) |
| Tunnel type | `cloudflared` (remotely managed) |
| Namespace | `cloudflare` |
| Chart | `helm/cloudflare/cloudflare-tunnel-remote-0.1.2-custom` |
| Credential secret | `cloudflared-credentials` (SealedSecret, key: `tunnelToken`) |

---

## Background

Homelab services under `*.app.jyje.online` were previously exposed by pointing CNAME records to a DDNS hostname (`&lt;ddns-hostname&gt;`), which resolves to the home public IP. This means:

- The home public IP is visible in public DNS
- Inbound port forwarding must be configured on the home router
- Moving ISPs or locations requires updating DDNS and router settings

---

## Solution

Use **Cloudflare Tunnel** (`cloudflared`) to create an outbound-only connection from the cluster to Cloudflare's edge. Traffic flows inward through the tunnel without any open inbound ports.

```
User → *.app.jyje.online
         ↓ (Porkbun CNAME → cfargotunnel.com)
         Cloudflare Edge
         ↓ (encrypted outbound tunnel)
         cloudflared Pod (namespace: cloudflare)
         ↓
         NGINX Ingress Controller
         ↓
         Service → Pod
```

**Benefits:**
- Home IP never appears in public DNS
- No router port forwarding required
- DDNS (`&lt;ddns-hostname&gt;`) no longer needed for public services
- Survives ISP changes and home moves without any configuration update

---

## Cloudflare Zero Trust Configuration

### Tunnel routes (Published application routes)

Configured in the Cloudflare Zero Trust dashboard under **Networks → Tunnels → [tunnel] → Published application routes**:

| # | Hostname | Path | Service |
|---|----------|------|---------|
| 1 | `app.jyje.online` | `*` | `http://ingress-nginx-controller.ingress.svc.cluster.local:80` |
| 2 | `*.app.jyje.online` | `*` | `http://ingress-nginx-controller.ingress.svc.cluster.local:80` |

Both routes forward all traffic to the NGINX Ingress controller, which handles per-hostname routing internally using existing Ingress rules.

> The `ingress` namespace assumes MicroK8s ingress addon. Verify with:
> `kubectl get svc -A | grep ingress-nginx-controller`

---

## Helm Chart

Vendored from the official Cloudflare Helm repository with two patches applied:

**Source:** `https://cloudflare.github.io/helm-charts`  
**Chart:** `cloudflare-tunnel-remote` v0.1.2  
**Stored as:** `helm/cloudflare/cloudflare-tunnel-remote-0.1.2-custom`

### Patches

**1. `secretName` support** (`templates/secret.yaml`, `templates/deployment.yaml`, `values.yaml`)

The upstream chart always creates a Secret from `cloudflare.tunnel_token` in values. The patch adds a `cloudflare.secretName` option: when set, the chart skips creating the Secret and references the named external Secret instead. This enables SealedSecret-based token management without plaintext values in Git.

```yaml
# values.yaml
cloudflare:
  tunnel_token: ""
  secretName: null  # set to use an external Secret
```

**2. `extraResources` support** (`templates/extra-resources.yaml`, `values.yaml`)

Standard repo patch to allow injecting arbitrary Kubernetes resources (e.g. SealedSecret) alongside the chart deployment.

---

## ArgoCD Application

**File:** `clusters/r4spi/apps/cloudflared.yaml`

Key values:

```yaml
cloudflare:
  secretName: cloudflared-credentials   # references SealedSecret below

extraResources:
  - apiVersion: bitnami.com/v1alpha1
    kind: SealedSecret
    metadata:
      name: cloudflared-credentials
    spec:
      encryptedData:
        tunnelToken: <sealed>
      template:
        metadata:
          name: cloudflared-credentials
        type: Opaque
```

---

## DNS Migration (Porkbun)

Individual CNAME records pointing to `&lt;ddns-hostname&gt;` are replaced with records pointing to `<tunnel-uuid>.cfargotunnel.com`.

### Target state

| Record | Type | Target |
|--------|------|--------|
| `app.jyje.online` | CNAME | `<tunnel-uuid>.cfargotunnel.com` |
| `*.app.jyje.online` | CNAME | `<tunnel-uuid>.cfargotunnel.com` |

### Migration order

Migrate one service at a time to validate tunnel connectivity before cutting over all records:

1. `portainer.app.jyje.online` — pilot record (migrated 2026-05-10)
2. Remaining `*.app.jyje.online` records — after pilot confirmed

### Old records (to be removed)

| Subdomain | Old target |
|-----------|-----------|
| `app` | `&lt;ddns-hostname&gt;` |
| `cd.app` | `&lt;ddns-hostname&gt;` |
| `homer.app` | `&lt;ddns-hostname&gt;` |
| `llm.app` | `&lt;ddns-hostname&gt;` |
| `milvus.app` | `&lt;ddns-hostname&gt;` |
| `n8n.app` | `&lt;ddns-hostname&gt;` |
| `portainer.app` | `&lt;ddns-hostname&gt;` ✅ migrated |
| `attu.app` | `&lt;ddns-hostname&gt;` |
| `infisical.app` | `&lt;ddns-hostname&gt;` |

---

## Seal a new token

If the tunnel token needs to be rotated:

```bash
kubectl create secret generic cloudflared-credentials \
  --namespace cloudflare \
  --from-literal=tunnelToken=<token> \
  --dry-run=client -o yaml | \
  kubeseal --format yaml
```

Copy the `encryptedData.tunnelToken` value into `clusters/r4spi/apps/cloudflared.yaml`.
