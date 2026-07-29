# Local patches

## `extraResources` support

The upstream chart supports `extraObjects` but does not expose this
repository's `extraResources` convention. This vendored copy adds:

- `templates/extra-resources.yaml`
- an `extraResources: []` values entry
- matching JSON schema support

This preserves the existing GitOps pattern for rendering related Kubernetes
resources alongside the chart without modifying upstream workloads.
