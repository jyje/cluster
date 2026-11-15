# Patches applied to upstream chart

This directory contains the vendored `higress` Helm chart (version 2.2.6, pulled
from https://higress.io/helm-charts) with the following patch applied on top of
the upstream release.

---

## [PATCH] Add `extraResources` support

**Reason:** The upstream chart has no built-in mechanism to deploy arbitrary
extra manifests alongside the release. This repo standardizes on injecting them
via an `extraResources` value on every vendored top-level chart, so related
resources can be declared inline in the ArgoCD Application.

### Changed files

| File | Change |
|------|--------|
| `values.yaml` | New file (the upstream umbrella chart has none). Adds `extraResources: []` |
| `templates/extra-resources.yaml` | New template: renders each `extraResources` entry as its own document |

### Notes

- Not an upstream chart feature. Re-vendoring to a newer upstream version
  requires re-applying this patch.
- The umbrella chart has no settings of its own. Higress options go under the
  `higress-core` and `higress-console` keys of the Application values.
- Canonical patch definition: `.claude/skills/helm-extraresources-patcher/SKILL.md`.
