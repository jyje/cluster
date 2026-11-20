# Local patch

- Source: `oci://ghcr.io/n8n-io/n8n-helm-chart/n8n:1.20.0`
- Tracking issue: #245
- Make the main startup probe configurable through `probes.startup` (`path`, `periodSeconds`, `failureThreshold`). Defaults match the upstream fixed values (`/healthz`, 10 s, 30 tries). Workers and the webhook processor are unchanged. Carried over from the 1.19.0 patch (tracking issue #256).
- The standard `extraResources` key, schema and renderer come from the vendoring step, not from this patch.
