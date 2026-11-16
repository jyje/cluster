---
name: helm-batch-upgrade
description: Bring every Argo CD Application up to the newest chart and image. Use when the user asks to upgrade all charts, to find what is behind, to catch up deployments with vendored charts, or to clean up old chart directories after a rollout. Covers the three gaps that a chart bump alone leaves open.
---

# Helm Batch Upgrade

> **Language:** Answer in the user's language.

A vendored chart that nobody points at is not deployed. Closing a Renovate tracking issue means the chart reached `helm/`, not that the cluster runs it. This skill finds and closes three separate gaps.

## The three gaps

| Gap | Where it hides | How to find it |
| :-- | :-- | :-- |
| 1. Not vendored | The upstream release is newer than anything in `helm/` | Compare the latest upstream release or `helm search repo --versions` with the newest directory in `helm/<group>/` |
| 2. Not deployed | An Application `path:` points at an older directory than the newest one in `helm/` | Run the scan below |
| 3. Image pinned | The Application sets an image tag, so the chart's `appVersion` is ignored | Audit every image reference in the Application values |

Do not trust a single signal. A chart can look current in `helm/` and still be behind upstream (gap 1), and an app can sit on the newest chart and still run an old image (gap 3).

## 1. Scan for gap 2

Run from the repository root. It prints every Application whose `path:` is not the newest directory next to it.

```bash
python3 - <<'PY'
import re, glob, os
from pathlib import Path
key = lambda v: [int(x) if x.isdigit() else x for x in re.split(r'[.\-]', v.lstrip('v'))]
for f in sorted(glob.glob('clusters/*/apps/*.yaml')):
    for m in re.finditer(r'path:\s*(helm/\S+/(\S+))\s*$', open(f).read(), re.M):
        d, cur = Path(m.group(1)).parent, m.group(2)
        mm = re.match(r'(.+?)-(v?\d.*)$', cur)
        if not mm or not d.is_dir():
            continue
        pre = mm.group(1)
        names = [p.name for p in d.iterdir() if re.match(re.escape(pre) + r'-v?\d', p.name)]
        best = max(names, key=lambda n: key(n[len(pre) + 1:]))
        if best != cur:
            print(os.path.basename(f), cur, '->', best)
PY
```

Run it on `origin/main`, not on a stale local checkout. Fetch first.

## 2. Check gap 1 against upstream

For each chart, read the newest upstream release, not only the newest directory in `helm/`. Use the provider listed in `helm/README.md`. Example for an OCI chart on GitHub: `gh release list --repo <owner>/<repo> --limit 5`.

Also check the upstream **image**, because a chart can lag its application. For Docker Hub: `curl -s "https://hub.docker.com/v2/repositories/<repo>/tags?page_size=15&ordering=last_updated"`.

Vendor missing charts with the `helm-chart-vendor` skill before changing any Application.

## 3. Audit image pins (gap 3)

For each Application you touch, list every image reference in its values, including init containers and extra containers:

```bash
grep -n -E '^\s*(tag|image|repository|version):|image:' clusters/*/apps/<app>.yaml
```

Classify each hit:

| Pin | Rule |
| :-- | :-- |
| Commented out or empty | Follows the chart `appVersion`. Leave it. |
| Floating `<major>.<minor>` | Intended auto-patch. Run `floating-image-tag-sync`. Do not pin a full version. |
| Full version equal to the old `appVersion` | A mirror of the chart. Move it to the new `appVersion` in the same commit. |
| Full version unrelated to the chart | Likely deliberate. Compare it with the new `appVersion`, report the gap, and ask before changing it. |
| `tag: managed` | Owned by Argo CD Image Updater. Leave it. |
| Init or extra container image | Not covered by `image.tag`. It often repeats the main image. Move it together with the main image. |

Always compare the pin with the **new** chart's `appVersion` and with the upstream latest image. A pin that was ahead of the old chart can fall behind the new one.

## 4. Verify before the PR

1. Render the old and the new chart with the Application's own values and compare:
   ```bash
   yq '.spec.source.helm.valuesObject' clusters/<cluster>/apps/<app>.yaml > "$KIROCREW_SCRATCH/values.yaml"
   helm template <release> helm/<group>/<chart-old> -f "$KIROCREW_SCRATCH/values.yaml" > "$KIROCREW_SCRATCH/old.yaml"
   helm template <release> helm/<group>/<chart-new> -f "$KIROCREW_SCRATCH/values.yaml" > "$KIROCREW_SCRATCH/new.yaml"
   diff "$KIROCREW_SCRATCH/old.yaml" "$KIROCREW_SCRATCH/new.yaml"
   ```
   Every changed line should be explained: an image, a label, or a documented default.
2. Run the values report from step 7 of `helm-chart-vendor` for charts that jump several versions or cross a major version.
3. Say plainly what you could not check, for example whether an init script still works on a new image.

## 5. Split the work

- One PR vendors new charts. One PR points Applications at them. Keep them apart so a bad rollout reverts without touching `helm/`.
- Put self-upgrading apps (Argo CD) and charts that jump many versions in the PR description as review items.
- Do not delete old chart directories in the same PR as the upgrade.

## 6. Clean up after a successful rollout

Only for charts whose Application already points at the newest vendored directory and whose rollout the user considers healthy. Skip any chart whose upgrade PR is still open.

1. **Keep the three most recent chart directories that were actually deployed.** Read them from the history of the Application `path:` on the default branch, newest first, not from the directory listing. A chart that was vendored but never deployed does not count.
2. **Always keep a directory that any Application uses now**, and any directory newer than the current one (vendored, waiting to be deployed).
3. **Delete the rest** of that chart family, in the same group folder, matching `<chart-name>-<version>`.
4. **Check for other references before deleting**, and keep a directory that something else needs:
   ```bash
   git grep -n -F "<chart-dir-name>" -- . ':!helm'
   ```
   Examples: a script or test that names a fixed old and new chart. Mentions inside skill examples are not dependencies.
5. Charts that no Application uses (kept on purpose, for example retired gateways) are not touched.
6. Use `git rm -r`, put it in its own PR with the `remove` type, and let the PR list what was kept. It can be reverted alone.

Real rollout health is not visible from the repository. Say so in the PR, and rely on the kept versions as rollback targets.

## Report format

Finish with one table per gap: chart, current, target, and what was changed or skipped. State which gaps you checked and which you did not.
