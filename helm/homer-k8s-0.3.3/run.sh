helm upgrade --install --cleanup-on-fail \
  --namespace homer-system --create-namespace \
  --set fullnameOverride=homer \
  homer .

helm uninstall homer --namespace homer-system
kubectl delete namespace homer-system
