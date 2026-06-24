---
name: manifest-group
description: Deploy a group of raw Kubernetes manifests via GitOps/ArgoCD without an underlying application chart, using the manifest-group shell chart. Use when a set of resources (ConfigMap, CRD instance, Ingress, RBAC, Job, etc.) needs to live in its own ArgoCD Application/namespace but doesn't belong to any existing Helm release.
---

# Manifest Group

> **Language:** Always communicate with the user in their language.

A minimal shell chart (`helm/jyje/manifest-group-0.1.0`) whose only job is to
render whatever is listed under `values.manifests`. Use it instead of
`manifests/<name>/` plain-YAML directories when you want Helm's `tpl`
rendering (e.g. `{{ .Release.Namespace }}`, `{{ .Release.Name }}`) available
inside the resources, or when you're already comfortable with the
`extraResources`-style pattern used throughout this repo's vendored charts.

## When to use this instead of alternatives

| Need | Use |
|------|-----|
| A few extra resources alongside an existing app's chart (e.g. a SealedSecret next to `litellm`) | That chart's own `extraResources` (see `helm-extraresources-patcher` skill) |
| A standalone group of resources with **no real application chart**, Helm templating wanted | **manifest-group** (this skill) |
| A standalone group of resources, plain YAML, no templating needed | `manifests/<name>/` directory (see `metallb-config` for an example) |

A concrete motivating case: `homer-operator` (the controller) and the actual
Homer `Dashboard` instance (ConfigMap + Dashboard CR + Ingress + restart-hook
Job/RBAC) have independent lifecycles — the controller's chart version
changes separately from the dashboard's content edits. Splitting them into
two ArgoCD Applications keeps a PostSync hook scoped to only the content
that actually needs it, instead of firing on every operator chart bump.

## Workflow

1. **Confirm the chart exists**: `helm/jyje/manifest-group-0.1.0/`. If a future
   version bump is needed, follow the `helm-chart-vendor` skill's versioning
   convention (`helm/jyje/manifest-group-<new-version>/`) — but since this is
   an internally-authored chart (no upstream source), just copy-edit the
   existing directory rather than `helm pull`.

2. **Create a new ArgoCD Application** under `clusters/<cluster>/apps/<name>.yaml`:
   ```yaml
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: <name>
   spec:
     project: base
     source:
       repoURL: https://github.com/jyje/cluster
       targetRevision: main
       path: helm/jyje/manifest-group-0.1.0
       helm:
         valuesObject:
           manifests:
             - apiVersion: v1
               kind: ConfigMap
               metadata:
                 name: example
                 namespace: "{{ .Release.Namespace }}"
               data:
                 key: value
     destination:
       server: https://kubernetes.default.svc
       namespace: <target-namespace>
     syncPolicy:
       automated:
         prune: true
         selfHeal: true
       syncOptions:
         - CreateNamespace=true
   ```

3. **List resources under `manifests:`**, one entry per Kubernetes object.
   Object format (preferred) or raw multiline string format both work — see
   `helm/jyje/manifest-group-0.1.0/values.yaml` for both examples. Each item is
   rendered through `tpl`, so `{{ .Release.Namespace }}`, `{{ .Release.Name }}`,
   and other Helm expressions are evaluated.

4. **Use `{{ .Release.Namespace }}` for the namespace** on every resource
   rather than hardcoding it, so the Application's `destination.namespace`
   stays the single source of truth.

5. **PostSync/PreSync hooks work normally** — add the standard
   `argocd.argoproj.io/hook` annotations to any Job/resource in the list, same
   as a regular Helm chart. See `homer-instance.yaml` for a working example
   (a restart-hook Job that runs after every sync).

6. **Verify rendering before committing**:
   ```bash
   cd helm/jyje/manifest-group-0.1.0
   yq '.spec.source.helm.valuesObject' ../../../clusters/<cluster>/apps/<name>.yaml > /tmp/values.yaml
   helm template . -f /tmp/values.yaml --namespace <target-namespace>
   ```
   Confirm every expected `kind:` appears and `{{ .Release.* }}` expressions
   resolved to literal values, not left as unrendered template syntax.

## Reference example

`clusters/r4spi/apps/homer-instance.yaml` — the Homer Dashboard instance
(ConfigMap, Dashboard CR, Ingress, restart-hook ServiceAccount/Role/
RoleBinding/Job), entirely deployed through this pattern, paired with
`clusters/r4spi/apps/homer-operator.yaml` (the operator/controller, a real
vendored chart) to show the separation of concerns this pattern enables.
