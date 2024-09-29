helm upgrade --install --cleanup-on-fail \
    -n argocd --create-namespace \
    -f charts/argo-cd-stack/values.yaml \
    argo-cd-stack \
    charts/argo-cd-stack 