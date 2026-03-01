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

---

## PostgreSQL credentials (infisical-postgresql)

The Infisical app uses PostgreSQL with credentials from a separate Secret so that:

- Passwords are not stored in Helm values or Git as plaintext.
- The chart mounts the secret as **files** under `/opt/bitnami/postgresql/secrets/` (`usePasswordFiles: true`).

The Application expects a Secret named `infisical-postgresql` with:

- `postgres-password` — password for the `postgres` admin user.
- `password` — password for the `infisical` application user (must match chart value used for the connection string, e.g. `root`).

**One-time setup:** create the secret, seal it, and paste the sealed `encryptedData` into `clusters/r4spi/apps/infisical.yaml` (SealedSecret `infisical-postgresql`).

```bash
# 1. Create namespace if needed
kubectl create namespace infisical --dry-run=client -o yaml | kubectl apply -f -

# 2. Create secret (use a strong postgres-password; password=root must match postgresql.auth.password in chart)
kubectl create secret generic infisical-postgresql -n infisical \
  --from-literal=postgres-password="$(openssl rand -base64 24)" \
  --from-literal=password=root \
  --dry-run=client -o yaml | kubeseal --controller-name sealed-secrets -o yaml

# 3. Copy the spec.encryptedData block from the output and replace the placeholder encryptedData
#    in clusters/r4spi/apps/infisical.yaml (SealedSecret infisical-postgresql).
```

After that, Argo CD sync will apply the SealedSecret and the controller will create the `infisical-postgresql` Secret; the PostgreSQL StatefulSet will use it and mount it under `/opt/bitnami/postgresql/secrets/`.
