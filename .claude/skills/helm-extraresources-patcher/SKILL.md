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
{{- range .Values.extraResources }}
---
{{- if typeIs "string" . }}
  {{- tpl . $ }}
{{- else }}
  {{- tpl (toYaml .) $ }}
{{- end }}
{{- end }}
```

Each item is rendered through `tpl`, so Helm template expressions (e.g. `{{ .Release.Namespace }}`) inside `extraResources` values are evaluated at render time. Both object and raw string formats are supported (see values.yaml below).

### B. Update values.yaml
Append the `extraResources: []` definition at the end of `<chart-dir>/values.yaml`:
```yaml

# -- Extra resources to deploy with the chart.
# Supports both object and string (multiline) formats. Helm template expressions are evaluated.
extraResources: []
  # Object format:
  # - apiVersion: v1
  #   kind: ConfigMap
  #   metadata:
  #     name: example-configmap
  #     namespace: "{{ .Release.Namespace }}"
  #   data:
  #     example-key: example-value
  #
  # String format (multiline):
  # - |
  #   apiVersion: v1
  #   kind: ConfigMap
  #   metadata:
  #     name: example-configmap
  #     namespace: "{{ .Release.Namespace }}"
```

### C. Update values.schema.json (Optional)
If `<chart-dir>/values.schema.json` exists, MUST add `extraResources` to the `properties` block:
```json
        "extraResources": {
            "type": "array",
            "items": {
                "oneOf": [
                    { "type": "string" },
                    { "type": "object" }
                ]
            }
        }
```
Failure to update the schema will cause `helm template` to fail if `additionalProperties: false` is set.

## 3. Verification

1. **Verify template rendering**:
   Run `helm template .` in the patched directory to ensure it doesn't break basic rendering.

2. **Test object format**:
   ```bash
   helm template . --set "extraResources[0].apiVersion=v1,extraResources[0].kind=ConfigMap,extraResources[0].metadata.name=test"
   ```

3. **Test string format with Helm expression**:
   ```bash
   helm template . --set-string 'extraResources[0]=apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n  namespace: "{{ .Release.Namespace }}"'
   ```
   Confirm that `{{ .Release.Namespace }}` is rendered as the actual namespace, not left as a literal string.
