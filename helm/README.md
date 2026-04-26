# Helm charts

We keep copies of Helm charts in this repository because upstream providers can change their policies or suffer outages, and in those situations the original chart may become unavailable or change in unexpected ways. Storing vendored copies here avoids losing the chart we depend on and keeps deployments reproducible.

This directory holds those vendored charts. Each chart lives under **`helm/<group>/<chart-name>-<version>/`**.

## Group and provider

- **Group** = folder under `helm/` (app/family name). One group can contain charts from multiple providers.
- **Provider** = Helm repo name used for `helm pull`. Same as group when one repo per family, or distinct when a group aggregates multiple sources (e.g. cert-manager: jetstack + adfinis).

When adding or upgrading a chart, use the table below to choose group and provider; then pull with `helm pull <provider>/<chart-name> --untar --version <version>` and place under `helm/<group>/<chart-name>-<version>/`.

## Group and provider (repo URL)

Top-level groups vendored here (dependency charts excluded). Check each group folder for chart versions.

| Group | Provider | URL |
|-------|----------|-----|
| actions-runner-controller | actions-runner-controller | https://actions-runner-controller.github.io/actions-runner-controller |
| argo | argo | https://argoproj.github.io/argo-helm |
| homer-k8s | bananaops | https://bananaops.github.io/homer-k8s |
| cert-manager | jetstack | https://charts.jetstack.io |
| cert-manager | adfinis | https://charts.adfinis.com |
| cnpg | cnpg | https://cloudnative-pg.github.io/charts |
| infisical | infisical | https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/ |
| ingress | ingress-nginx | https://kubernetes.github.io/ingress-nginx |
| istio | istio | https://istio-release.storage.googleapis.com/charts |
| jyje | — | (this repo; no external Helm repo) |
| litellm | berriai | oci://docker.litellm.ai/berriai/litellm-helm |
| longhorn | longhorn | https://charts.longhorn.io |
| metrics-server | metrics-server | https://kubernetes-sigs.github.io/metrics-server |
| milvus | milvus | https://zilliztech.github.io/milvus-helm/ |
| nfs-subdir-external-provisioner | nfs-subdir-external-provisioner | https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/ |
| nvidia | nvidia | https://helm.ngc.nvidia.com/nvidia |
| ollama-helm | ollama-helm | https://otwld.github.io/ollama-helm/ |
| open-webui | open-webui | https://helm.openwebui.com/ |
| portainer | portainer | https://portainer.github.io/k8s/ |
| qdrant | qdrant | https://qdrant.github.io/qdrant-helm |
| sealed-secrets | sealed-secrets | https://bitnami-labs.github.io/sealed-secrets |
| seaweedfs | seaweedfs | https://seaweedfs.github.io/seaweedfs/helm |
| seaweedfs | seaweedfs-csi-driver | https://seaweedfs.github.io/seaweedfs-csi-driver/helm |
