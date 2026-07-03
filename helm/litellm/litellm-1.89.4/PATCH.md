# Patches applied to upstream chart

This directory contains the vendored `litellm` Helm chart (version 1.89.4) with
the following patches applied on top of the upstream release.

---

## [PATCH] Replace Bitnami init-container images with SolDevelo equivalents

**Source:** [jyje/cluster#34](https://github.com/jyje/cluster/pull/34)  
**Reason:** Bitnami (Broadcom) restricted public registry access effective
2025-08-28. Pulling `bitnami/*` images without a VMware Tanzu subscription now
fails. SolDevelo provides drop-in replacements built from the same open-source
Dockerfiles ([SolDevelo/containers](https://github.com/SolDevelo/containers)).

### Changed files

| File | Field | Before | After |
|------|-------|--------|-------|
| `charts/postgresql/values.yaml` | `volumePermissions.image` | `bitnami/os-shell:12-debian-12-r16` | `soldevelo/os-shell:12-debian-12-r3` |
| `charts/redis/values.yaml` | `volumePermissions.image` | `bitnami/os-shell:12-debian-12-r16` | `soldevelo/os-shell:12-debian-12-r3` |
| `charts/redis/values.yaml` | `sysctl.image` | `bitnami/os-shell:12-debian-12-r16` | `soldevelo/os-shell:12-debian-12-r3` |
| `templates/tests/test-servicemonitor.yaml` | `containers[0].image` | `bitnami/kubectl:latest` | `soldevelo/kubectl:latest` |

### Notes

- Only init-container / test-hook images are replaced; workload images
  (postgresql, redis, redis-sentinel, etc.) are unchanged.
- The `kubectl.image` entry in `charts/redis/values.yaml` (`1.29.2-debian-12-r3`)
  is **not** patched because SolDevelo does not publish that specific tag.
  That image is used only by the optional master-label update job
  (`kubectl.enabled: false` by default).
- Re-vendoring this chart to a newer upstream version will require re-applying
  these substitutions.
