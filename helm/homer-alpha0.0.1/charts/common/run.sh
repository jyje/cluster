helm upgrade --cleanup-on-fail \
    -n homer --create-namespace \
    --install \
    -f values.yaml \
    homer .

helm uninstall homer -n homer
