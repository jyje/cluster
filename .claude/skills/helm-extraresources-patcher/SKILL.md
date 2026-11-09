---
name: helm-extraresources-patcher
description: ensure all Helm charts have 'extraResources' support by patching templates/extra-resources.yaml and values.yaml. Run when searching for root charts or when a new chart is added.
---

# Helm ExtraResources Patcher

This skill ensures that all vendored top-level Helm charts in the repository support injecting arbitrary Kubernetes resources via the `extraResources` value. This is useful for adding related resources like `SealedSecrets` or `CloudNativePG Cluster` without modifying upstream chart templates.

> [!IMPORTANT]
> - **Main Charts Only**: Never patch subcharts (directories inside `charts/`).
> - **Exact-name rule**: Use only the top-level `extraResources` key in repository-owned Helm values for resource injection. Names such as `extraObjects` and `extraDeploy` do not substitute for it. Keep those upstream features intact and add the standard patch alongside them.
> - **Preserve native support**: If the chart already declares `extraResources`, keep its values, schema, and renderer unchanged. If a required probe fails, report the incompatibility instead of adding a second renderer for the same key.
> - **Probe contract**: Both formats are required by default. Only charts listed in the [object-only policy](../../../helm-sources/extra-resources-policy.json) use the object probe alone. For those charts, reject YAML strings and Helm expressions inside objects.

## 1. Audit Phase

1. **Locate top-level charts**:
   ```bash
   find helm -name Chart.yaml -not -path "*/charts/*" | xargs -n 1 dirname | sort -u
   ```

2. **Check the exact key**:
   - Inspect the top-level `extraResources` key in `values.yaml` for the chart version being added.
   - If present, skip patching and go directly to verification. If absent, apply the standard patch. Do not overwrite an unrelated template at the canonical path.

## 2. Patching Phase

For a new chart version without a top-level `extraResources` key:

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
Append the `extraResources: []` definition:
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

3. **Test string format with Helm expression** (unless the object-only policy applies):
   ```bash
   helm template . --set-string 'extraResources[0]=apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n  namespace: "{{ .Release.Namespace }}"'
   ```
   Confirm that `{{ .Release.Namespace }}` is rendered as the actual namespace, not left as a literal string.
