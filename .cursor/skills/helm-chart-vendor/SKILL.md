---
name: helm-chart-vendor
description: Pull a Helm chart from a repo at a specific version and save it under helm/ with a versioned directory name. Use when adding or upgrading a vendored Helm chart, when the user asks to vendor a chart, or when following the repo's "add chart to helm/" workflow.
---

# Helm Chart Vendor

Pull a Helm chart from an external repo at a specific version and store it under `helm/` as `<chart-name>-<version>`. Used to pin versions for reproducible deployments.

## Workflow

1. **Update repos** (optional, when you need the latest index)
   ```bash
   helm repo update
   ```

2. **List available versions**
   ```bash
   helm search repo <repo-name>/<chart-name> --versions
   ```
   e.g. `helm search repo open-webui/open-webui --versions`

3. **Download and untar the chart**
   ```bash
   helm pull <repo-name>/<chart-name> --untar --version <version>
   ```
   e.g. `helm pull open-webui/open-webui --untar --version 12.5.0`

4. **Rename the directory to include the version**
   ```bash
   mv <chart-name>/ <chart-name>-<version>/
   ```
   e.g. `mv open-webui/ open-webui-12.5.0/`

Run from the project root’s **helm/** directory. If already inside `helm/`, run the commands as-is.

## Convention

- Storage path: `helm/<chart-name>-<version>/`
- Always suffix the directory name with the **version** to distinguish from other chart versions.

## Example (end-to-end)

```bash
cd helm
helm repo update
helm search repo open-webui/open-webui --versions
helm pull open-webui/open-webui --untar --version 12.5.0
mv open-webui/ open-webui-12.5.0/
```

Argo CD or Helm apps can then reference `helm/open-webui-12.5.0` as the chart path.
