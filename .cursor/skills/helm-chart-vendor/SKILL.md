---
name: helm-chart-vendor
description: Pull a Helm chart from a repo (or OCI) at a specific version and save it under helm/<group>/ with a versioned directory name. Use when adding or upgrading a vendored Helm chart, when the user asks to vendor a chart, or when following the repo's "add chart to helm/" workflow.
---

# Helm Chart Vendor

Pull a Helm chart from an external repo (or OCI) at a specific version and store it under **`helm/<group>/<chart-name>-<version>/`**. Used to pin versions for reproducible deployments.

## Group folder

- **Path:** `helm/<group>/`
- **Group name:** 1st priority = name used in this repo (e.g. app/family name); 2nd = official Helm repo name.
- Example: ARC charts from `actions-runner-controller` repo are grouped as `github-actions-runner-controller` (repo app name).

## Chart directory name

- **Format:** `<original-chart-name>-<version>` (no group prefix; the group folder already identifies the family).
- Examples: `gha-runner-scale-set-controller-0.13.1`, `open-webui-12.5.0`.

## Workflow

1. **Update repos** (optional, when you need the latest index)
   ```bash
   helm repo update
   ```

2. **Determine group**  
   Use repo app name (1st) or Helm repo name (2nd). Create `helm/<group>/` if it does not exist.

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
- **Group:** 1st = this repo’s name for the family, 2nd = Helm repo name.
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

## Chart (group) name and repo URL

Top-level charts/groups vendored in this repo (dependency charts excluded). Check the `helm/` directory for versions.

| Chart (group) name | URL |
|-----------------|------|
| actions-runner-controller | https://actions-runner-controller.github.io/actions-runner-controller |
| argo | https://argoproj.github.io/argo-helm |
| bananaops | https://bananaops.github.io/homer-k8s |
| cnpg | https://cloudnative-pg.github.io/charts |
| infisical | https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/ |
| ingress-nginx | https://kubernetes.github.io/ingress-nginx |
| istio | https://istio-release.storage.googleapis.com/charts |
| jetstack | https://charts.jetstack.io |
| jyje | https://jyje.github.io/helm-charts/charts |
| longhorn | https://charts.longhorn.io |
| metrics-server | https://kubernetes-sigs.github.io/metrics-server |
| milvus | https://zilliztech.github.io/milvus-helm/ |
| nfs-subdir-external-provisioner | https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/ |
| nvidia | https://helm.ngc.nvidia.com/nvidia |
| ollama-helm | https://otwld.github.io/ollama-helm/ |
| open-webui | https://helm.openwebui.com/ |
| portainer | https://portainer.github.io/k8s/ |
| sealed-secrets | https://bitnami-labs.github.io/sealed-secrets |
