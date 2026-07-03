# Patches applied to upstream chart

This directory contains the vendored `base` Helm chart (version 1.29.0)
with the following patches applied on top of the upstream release.

---

## [PATCH] Add `extraResources` support

**Reason:** The upstream chart has no built-in mechanism to deploy arbitrary
extra manifests (e.g. SealedSecrets, CloudNativePG Clusters) alongside the
release. This repo standardizes on injecting them via an `extraResources`
value on every vendored top-level chart, so related resources can be declared
inline in the ArgoCD Application instead of as separate manifest files.

### Changed files

| File | Change |
|------|--------|
| `values.yaml` | Add `extraResources: []` value (object or templated-string entries) |
| `templates/extra-resources.yaml` | New template: renders each `extraResources` entry as its own document |

### Notes

- Not an upstream chart feature — re-vendoring to a newer upstream version
  requires re-applying this patch.
- Canonical patch definition: `.claude/skills/helm-extraresources-patcher/SKILL.md`.
