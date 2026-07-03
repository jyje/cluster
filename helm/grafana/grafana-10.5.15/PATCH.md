# Patches applied to upstream chart

This directory contains the vendored `grafana` Helm chart (version 10.5.15,
appVersion 12.3.1) with the following patches applied on top of the upstream
release.

---

## [PATCH] Add `extraResources` support

**Reason:** The upstream chart has no mechanism to deploy arbitrary extra
manifests alongside the release. This cluster needs to ship the Grafana admin
credentials (SealedSecret) and its CloudNativePG database (`Cluster`) inline
with the ArgoCD Application, rather than as separate manifest files, so the
whole Grafana stack stays declared in one place.

### Changed files

| File | Change |
|------|--------|
| `values.yaml` | Add `extraResources: []` value, documented as accepting both object and string (templated) entries |
| `templates/extra-resources.yaml` | New template: iterates `.Values.extraResources`, rendering each entry as its own document (`tpl` for strings, `toYaml` for objects) |

### Usage

Consumers set `extraResources` in their `valuesObject` to inject additional
resources, e.g. a `SealedSecret` for admin credentials or a `postgresql.cnpg.io/v1
Cluster` for the backing database. See
`clusters/r4spi/apps/lgtm-grafana.yaml` for the live example.

### Notes

- This is not an upstream chart feature — re-vendoring this chart to a newer
  upstream version will require re-applying this patch.
- Originally added in commit `9089a75` together with the CNPG database
  migration; documented here in retrospect.
