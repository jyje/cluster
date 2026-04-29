---
name: ambient-namespace-enroll
description: Enroll a namespace into Istio Ambient Mesh by adding managedNamespaceMetadata to the representative ArgoCD Application for that namespace. Use when the user asks to add a namespace to ambient mesh, enable ambient mode for a namespace, or apply istio.io/dataplane-mode=ambient to a namespace via GitOps.
---

# Ambient Namespace Enroll

Enroll a Kubernetes namespace into Istio Ambient Mesh via GitOps by patching the **representative ArgoCD Application** for that namespace.

## Rule: Representative Application

The representative application for a namespace is the ArgoCD `Application` that satisfies **all** of the following:
- `spec.destination.namespace` matches the target namespace
- `spec.syncPolicy.syncOptions` includes `CreateNamespace=true`
- It is the primary/main workload app for that namespace (not a supporting app like a database or secret)

If multiple apps deploy to the same namespace, choose the one that owns the namespace lifecycle (typically the app sharing its name with the namespace or the one explicitly creating it).

## What to add

Add `managedNamespaceMetadata` to the app's `syncPolicy`. The `CreateNamespace=true` syncOption **must already be present** for this to take effect.

```yaml
syncPolicy:
  managedNamespaceMetadata:
    labels:
      istio.io/dataplane-mode: ambient
  syncOptions:
    - CreateNamespace=true   # must be present
  automated: {}
```

## Workflow

1. **Identify the target namespace** from the user's request.

2. **Find the representative app** in `clusters/r4spi/apps/`:
   ```bash
   grep -l "namespace: <target-namespace>" clusters/r4spi/apps/*.yaml
   ```
   Then confirm it has `CreateNamespace=true`.

3. **Read the file** before editing.

4. **Patch `syncPolicy`**: add `managedNamespaceMetadata.labels` block directly above `syncOptions`.

5. **Verify**: confirm `CreateNamespace=true` is present in the same `syncPolicy`.

## Example

Target namespace: `homer-system` → representative app: `clusters/r4spi/apps/homer.yaml`

Before:
```yaml
syncPolicy:
  syncOptions:
    - CreateNamespace=true
  automated: {}
```

After:
```yaml
syncPolicy:
  managedNamespaceMetadata:
    labels:
      istio.io/dataplane-mode: ambient
  syncOptions:
    - CreateNamespace=true
  automated: {}
```

## Notes

- Do **not** create a separate `Namespace` resource for the label — `managedNamespaceMetadata` is the GitOps-native approach.
- Do **not** apply this to supporting apps (databases, secrets managers) that share a namespace — only the representative app.
- After committing, ArgoCD will apply the label on the next sync. No manual `kubectl label` needed.
