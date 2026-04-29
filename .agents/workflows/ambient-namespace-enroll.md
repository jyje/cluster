---
description: enroll a namespace into Istio Ambient Mesh by adding an explicit Namespace resource with istio.io/dataplane-mode=ambient via extraResources in the representative ArgoCD Application
---

# Ambient Namespace Enroll

Enroll a Kubernetes namespace into Istio Ambient Mesh via GitOps by declaring an explicit `Namespace` resource with the ambient label in the **representative ArgoCD Application**'s `extraResources`.

## Rule: Representative Application

The representative application for a namespace is the ArgoCD `Application` that satisfies **all** of the following:
- `spec.destination.namespace` matches the target namespace
- `spec.syncPolicy.syncOptions` includes `CreateNamespace=true`
- It is the primary/main workload app for that namespace (not a supporting app like a database or secret)

If multiple apps deploy to the same namespace, choose the one that owns the namespace lifecycle (typically the app sharing its name with the namespace or the one explicitly creating it).

## What to add

Add a `Namespace` resource under `valuesObject.extraResources` in the ArgoCD Application. This is fully GitOps-reproducible on any cluster state — no imperative steps required.

```yaml
helm:
  valuesObject:
    extraResources:
      - apiVersion: v1
        kind: Namespace
        metadata:
          name: <target-namespace>
          labels:
            istio.io/dataplane-mode: ambient
```

> **Prerequisite**: the chart must support `extraResources`. All vendored charts in this repo are patched by the `helm-extraresources-patcher` skill. Verify with `grep -n "extraResources" helm/<group>/<chart>/values.yaml`.

## Workflow

1. **Identify the target namespace** from the user's request.

2. **Find the representative app** in `clusters/r4spi/apps/`:
   ```bash
   grep -l "namespace: <target-namespace>" clusters/r4spi/apps/*.yaml
   ```
   Then confirm it has `CreateNamespace=true`.

3. **Read the file** before editing.

4. **Add `extraResources`** under `spec.source.helm.valuesObject` with the Namespace manifest.

5. **Verify**: confirm `CreateNamespace=true` is present in the same `syncPolicy`.

## Example

Target namespace: `homer-system` → representative app: `clusters/r4spi/apps/homer.yaml`

Before:
```yaml
helm:
  valuesObject:
    homer:
      image:
        tag: v25.11.1
syncPolicy:
  syncOptions:
    - CreateNamespace=true
  automated: {}
```

After:
```yaml
helm:
  valuesObject:
    homer:
      image:
        tag: v25.11.1
    extraResources:
      - apiVersion: v1
        kind: Namespace
        metadata:
          name: homer-system
          labels:
            istio.io/dataplane-mode: ambient
syncPolicy:
  syncOptions:
    - CreateNamespace=true
  automated: {}
```

## Notes

- This approach works regardless of whether the namespace pre-exists or is newly created — no `kubectl annotate` required.
- Do **not** apply this to supporting apps (databases, secrets managers) that share a namespace — only the representative app.
- If `automated.prune: true` is set on the app, deleting the app will also delete the Namespace and all its workloads. Keep `prune` unset or `false` if this is undesirable.
- After committing, ArgoCD will reconcile the Namespace resource on the next sync and apply the label.
