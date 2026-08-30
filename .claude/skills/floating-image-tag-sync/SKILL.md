---
name: floating-image-tag-sync
description: Keep an Application's floating minor-version image tag (e.g. tag "0.10") in sync with the vendored chart's appVersion when bumping a chart. Use during/after helm-chart-vendor whenever the app under `helm:` sets `image.tag` (or similar) to a bare "<major>.<minor>" string rather than a full "<major>.<minor>.<patch>" or empty string.
---

# Floating Image Tag Sync

Some Applications intentionally pin `image.tag` (or an equivalent field) to a
**floating minor-version tag** — e.g. `tag: "0.10"` instead of `tag: "0.10.4"`
or leaving it empty to track the chart's `appVersion`. The upstream image
registry resolves `0.10` to the latest `0.10.x` patch build, so patch releases
roll out automatically without touching this repo. This is a deliberate
trade-off (auto-patch vs. fully pinned reproducibility), not an oversight —
don't "fix" it by pinning a full version unless asked.

The trade-off only holds if the floating tag's minor version is kept in step
with the chart's own `appVersion` minor version. When the chart bumps a minor
version (its `appVersion` changes from `X.Y.*` to `X.(Y+1).*`), a stale
floating tag left at `X.Y` silently pins the running image to the *old* minor
line forever — it keeps "auto-following" patches that no longer exist,
because the registry has moved on. That defeats the reason this pattern
exists at all.

## When to run this

Immediately after (or as part of) `helm-chart-vendor`'s upgrade workflow, for
every Application manifest touched by the bump:

1. Find floating-tag fields in the touched `clusters/*/apps/<app>.yaml`:
   ```bash
   grep -nE '(tag|version):\s*"?[0-9]+\.[0-9]+"?\s*$' clusters/*/apps/<app>.yaml
   ```
   A match is "floating" only if it has exactly `<major>.<minor>` — no patch
   segment, no `v` prefix ambiguity. A full `X.Y.Z` pin or an empty string is
   a different, deliberate policy; leave those alone.

2. Compare the matched tag's `<major>.<minor>` against the **new** chart's
   `appVersion` (from the freshly vendored `Chart.yaml`), reduced to its own
   `<major>.<minor>`.

3. If they differ, update the floating tag to the new chart's
   `<major>.<minor>` in the same commit as the chart bump. If they already
   match, no change needed — say so explicitly rather than silently skipping.

## Report back

State plainly which Applications had a floating tag, whether it needed
bumping, and the before/after value. This is a targeted, mechanical field
edit — it doesn't need a diff-review confirmation gate the way a values.yaml
upgrade does, but it should be called out in the same PR description as the
chart bump so a reviewer isn't surprised by the extra line.
