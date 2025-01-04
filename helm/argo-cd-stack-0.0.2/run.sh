helm upgrade --install --cleanup-on-fail \
    -n argocd --create-namespace \
    -f helm/argo-cd-stack-0.0.2/values.yaml \
    argo-cd-stack \
    helm/argo-cd-stack-0.0.2
