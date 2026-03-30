---
name: helm-extraresources-patcher
description: ensure all Helm charts have 'extraResources' support by patching templates/extra-resources.yaml and values.yaml. Run when searching for root charts or when a new chart is added.
---

# Helm ExtraResources Patcher

This skill ensures that all vendored top-level Helm charts in the repository support injecting arbitrary Kubernetes resources via the `extraResources` value. This is useful for adding related resources like `SealedSecrets` or `CloudNativePG Cluster` without modifying upstream chart templates.

> [!IMPORTANT]
> - **Main Charts Only**: Never patch subcharts (directories inside `charts/`).
> - **Semantic Audit**: Before patching, check if the chart already supports a similar feature under a different name (e.g., `extraObjects`, `customResources`, `additionalResources`). If it does, do NOT add a redundant `extraResources` field.

## 1. Audit Phase

1. **Locate top-level charts**:
   ```bash
   find helm -name Chart.yaml -not -path "*/charts/*" | xargs -n 1 dirname | sort -u
   ```

2. **Evaluate existing support**:
   For each chart directory `<chart-dir>`:
   - Check `<chart-dir>/values.yaml` for keys like `extraResources`, `extraObjects`, `extraDeploy`.
   - If a key exists, search `grep -r` inside `<chart-dir>/templates` to see if that key is actually being used in any template.
   - If it is already used, the chart satisfies the requirement.

## 2. Patching Phase

If a chart has NO mechanism for injecting extra external resources:

### A. Add template file
Create `<chart-dir>/templates/extra-resources.yaml` with the following content:
```yaml
{{- if .Values.extraResources }}
{{- range .Values.extraResources }}
---
{{ toYaml . | nindent 0 }}
{{- end }}
{{- end }}
```

### B. Update values.yaml
Append the `extraResources: []` definition at the end of `<chart-dir>/values.yaml`:
```yaml

# -- Extra resources to deploy with the chart
extraResources: []
  # - apiVersion: v1
  #   kind: ConfigMap
  #   metadata:
  #     name: example-configmap
  #   data:
  #     example-key: example-value
```

## 3. Verification

1. **Verify template rendering**:
   Run `helm template .` in the patched directory to ensure it doesn't break basic rendering.
   
2. **Test injection**:
   Verify functionality by setting a test resource:
   ```bash
   helm template . --set "extraResources[0].apiVersion=v1,extraResources[0].kind=ConfigMap,extraResources[0].metadata.name=test"
   ```
