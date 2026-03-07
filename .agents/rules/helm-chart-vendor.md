---
description: Pull a Helm chart from a repo (or OCI) at a specific version and save it under helm/<group>/ with a versioned directory name. Use when adding or upgrading a vendored Helm chart, when the user asks to vendor a chart, or when following the repo's "add chart to helm/" workflow.
---

# Helm Chart Vendor

Pull a Helm chart from an external repo (or OCI) at a specific version and store it under **`helm/<group>/<chart-name>-<version>/`**. Used to pin versions for reproducible deployments.

## Group folder

- **Path:** `helm/<group>/`
- **Group name:** 1st priority = name used in this repo (e.g. app/family name); 2nd = official Helm repo name.
- A group can contain charts from **multiple providers** (e.g. `cert-manager`: controller from jetstack, issuers from adfinis). Group and provider are tracked separately; they may be the same (one provider per group) or different (one group, multiple providers).
- Example: ARC charts from `actions-runner-controller` repo are grouped as `github-actions-runner-controller` (repo app name).

## Chart directory name

- **Format:** `<original-chart-name>-<version>` (no group prefix; the group folder already identifies the family).
- Examples: `gha-runner-scale-set-controller-0.13.1`, `open-webui-12.5.0`.

## Workflow

1. **Update repos** (optional, when you need the latest index)
   ```bash
   helm repo update
   ```

2. **Determine group and provider**  
   **Group** = folder under `helm/` (e.g. app/family name; can aggregate multiple providers). **Provider** = Helm repo name for `helm pull`. **See `helm/README.md`** in this repo for the canonical list of groups and providers (Group | Provider | URL). Create `helm/<group>/` if it does not exist.

3. **List available versions**
   - **Helm repo:** `helm search repo <repo-name>/<chart-name> --versions`
   - **OCI:** `helm show chart oci://<registry>/<path>` or check registry/release notes for versions.

4. **Download and untar**
   - **Helm repo:**
     ```bash
     helm pull <repo-name>/<chart-name> --untar --version <version>
     ```
   - **OCI:**
     ```bash
     helm pull oci://<registry>/<path> --untar --version <version>
     ```
     e.g. `helm pull oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller --untar --version 0.13.1`

5. **Rename and place under group**
   ```bash
   mv <chart-name>/ <chart-name>-<version>/
   mv <chart-name>-<version>/ helm/<group>/
   ```
   Run from project root. If already in `helm/`, use `mv <chart-name>-<version>/ ../<group>/` or equivalent.

## Convention summary

- **Storage path:** `helm/<group>/<chart-name>-<version>/`
- **Group:** folder name (app/family); can be shared by multiple providers (see `helm/README.md`).
- **Provider:** Helm repo used for `helm pull`; same as group when one repo per family, or distinct (e.g. cert-manager: jetstack + adfinis).
- **Chart dir:** original chart name + `-<version>` only.

## Example (Helm repo)

```bash
cd helm
helm repo update
helm search repo open-webui/open-webui --versions
helm pull open-webui/open-webui --untar --version 12.5.0
mv open-webui/ open-webui-12.5.0
mkdir -p open-webui
mv open-webui-12.5.0 open-webui/
```

App path: `helm/open-webui/open-webui-12.5.0`

## Example (grouped + OCI)

```bash
cd helm
mkdir -p github-actions-runner-controller
helm pull oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller --untar --version 0.13.1
mv gha-runner-scale-set-controller gha-runner-scale-set-controller-0.13.1
mv gha-runner-scale-set-controller-0.13.1 github-actions-runner-controller/
```

App path: `helm/github-actions-runner-controller/gha-runner-scale-set-controller-0.13.1`

Argo CD or Helm apps reference `helm/<group>/<chart-name>-<version>` as the chart path.

## Group and provider

The canonical list of **Group | Provider | URL** is maintained in **`helm/README.md`** in this repo. When determining group/provider or adding a new chart, refer to that file.
