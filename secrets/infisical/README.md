# Infisical secrets (infisical-secrets)

Backend credentials for the Infisical standalone deployment. The chart expects a Secret named `infisical-secrets` in the `infisical` namespace.

## Official guide

Create the secret with at least:

- `AUTH_SECRET` — random base64 (e.g. `openssl rand -base64 32`)
- `ENCRYPTION_KEY` — random hex (e.g. `openssl rand -hex 16`)
- `SITE_URL` — absolute URL including protocol (must match how users reach the app)

## Direct creation (ingress-aware)

For ingress at `https://infisical.app.jyje.online`:

```bash
# Ensure namespace exists
kubectl create namespace infisical --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic infisical-secrets \
  --namespace infisical \
  --from-literal=AUTH_SECRET="$(openssl rand -base64 32)" \
  --from-literal=ENCRYPTION_KEY="$(openssl rand -hex 16)" \
  --from-literal=SITE_URL="https://infisical.app.jyje.online"
```

Use `SITE_URL` with `https` and the actual ingress host; do not use `http://localhost` when serving via ingress.

## SealedSecret

After creating `infisical-secrets` in the cluster (see above), seal it and save the SealedSecret into this repo. The controller in this cluster is named `sealed-secrets`.

```bash
# From repo root; requires kubeseal and cluster access
kubectl get secret infisical-secrets -n infisical -o yaml \
  | kubeseal --controller-name sealed-secrets -o yaml \
  > secrets/infisical/sealedsecret-infisical-secrets.yaml
```

Commit the generated file, then apply via Argo CD or:

```bash
kubectl apply -f secrets/infisical/sealedsecret-infisical-secrets.yaml
```

The sealed-secrets controller will create/update the `infisical-secrets` Secret in the `infisical` namespace from the SealedSecret.
