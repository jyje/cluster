# Local patch

- Source: `oci://ghcr.io/n8n-io/n8n-helm-chart/n8n:1.19.0`
- OCI digest: `sha256:13b8065b5e3dc657800c300fee36e976f692bb1382930c2ff317944814762943`
- Add the standard `extraResources` key, schema, and renderer. Preserve the upstream `extraObjects` implementation.
- Tracking issue: #256
- Make the main startup probe configurable through `probes.startup` (`path`, `periodSeconds`, `failureThreshold`). Defaults match the upstream fixed values (`/healthz`, 10 s, 30 tries). Workers and the webhook processor are unchanged.
