# Apache Airflow

Airflow 3.4.0 runs on the official Helm chart 1.22.0 with the `KubernetesExecutor`. It is the external endpoint of the [pilot-airflow-portability](https://github.com/jyje/pilot-airflow-portability) project. Tracking issue: #407.

## What runs

| Part | Choice |
| :-- | :-- |
| Namespace, Argo CD project | `airflow`, `ai` |
| Chart | `helm/airflow/airflow-1.22.0` (official, one local patch: the standard `extraResources` key) |
| Image | `apache/airflow:3.4.0` (the chart default is 3.2.2, so the Application pins it) |
| Executor | `KubernetesExecutor`: one task, one Pod. No Redis, Celery workers, Flower or statsd. The triggerer is off. |
| Components | api-server, scheduler and dag-processor, one replica each |
| Metadata database | CloudNativePG cluster `airflow-pg` (2 instances), Application `airflow-pg` |
| DAGs | `git-sync` from the public pilot repository, `src/dags`, branch `main`, every 60 seconds |
| Task logs | shared volume `subdir-usb` (2Gi), because task Pods are short lived |
| Endpoint | `https://airflow.app.jyje.online` (Higress, Let's Encrypt, route limit 20 requests per second) |
| Sign-in | authentik (OpenID Connect). The local `admin` user stays for API clients and as a fallback. |

The two Applications are separate on purpose: the database has its own lifecycle, and each workload keeps its own file.

## Secrets

No secret value is in git in plain text. Eight SealedSecrets in the Airflow Applications hold them, and one more in authentik:

| Secret | Used for |
| :-- | :-- |
| `airflow-pg-creds` | owner of the `airflow` database (CloudNativePG initdb) |
| `airflow-metadata` | the SQLAlchemy connection string (same password as above) |
| `airflow-fernet` | Fernet key for stored connections and variables |
| `airflow-api-secret` | API secret key |
| `airflow-jwt` | JWT signing secret, stable across restarts and replicas |
| `airflow-admin` | password of the `admin` user |
| `airflow-oidc` | OAuth client secret for authentik sign-in |
| `airflow-pilot` | password of the limited pilot API user |
| `authentik-airflow-oidc` | (in the authentik Application) the sealed blueprint with the same client secret |

Read the admin password from the cluster, never from git:

```bash
kubectl -n airflow get secret airflow-admin -o jsonpath='{.data.password}' | base64 -d
```

Rotating the OAuth client secret means resealing both `airflow-oidc` and `authentik-airflow-oidc` with the same new value. Rotating any other value means sealing a new Secret with the same name and namespace and replacing its entry in the Application. Rotating the JWT secret signs every user out. Rotating the Fernet key needs `airflow rotate-fernet-key`, or stored connections can no longer be read.

## Signing in with authentik

People sign in through authentik. The application `airflow` is created by the sealed blueprint `authentik-airflow-oidc` and is bound to `AuthentikAdmin` (which also admits `ClusterAdmin`), like the other admin tools. Airflow reads the `groups` claim of the ID token and maps it to a role in `apiServerConfig` of the Application:

| authentik group | Airflow role |
| :-- | :-- |
| `AuthentikAdmin` | `Admin` |
| `ClusterAdmin` | `Admin` |

No person is named in git. To make someone an Airflow admin, add their authentik account to `AuthentikAdmin` (see [authentik-access.md](authentik-access.md)). Roles are synced at every login, so removing the group removes the role at the next sign-in. Accounts that sign in but match no group get the `Public` role and can do nothing.

The redirect URI is `https://airflow.app.jyje.online/auth/oauth-authorized/authentik`. If sign-in fails, check the provider settings in authentik first (grant types, redirect URI, and the binding).

## DNS

The host `airflow.app.jyje.online` needs a CNAME record at the DNS provider, like the other `app` hosts. DNS is not managed from this repository, so this is a manual step. Until the name resolves, cert-manager cannot finish the HTTP-01 challenge: the Certificate stays `False` and the Challenge reports `no such host`. Add the record, and the certificate is issued within a minute or two. A new Application host needs the same step.

## Using the API

Airflow 3 has an authenticated public API. A client first gets a JWT from `/auth/token`, then sends it as a bearer token. A token from `/auth/token` lives 24 hours (`api_auth.jwt_expiration_time`, 86400). The CLI token lives 1 hour (`jwt_cli_expiration_time`, 3600). Both are the defaults, and the Application does not change them.

```bash
TOKEN=$(curl -s -X POST https://airflow.app.jyje.online/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<password>"}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" https://airflow.app.jyje.online/api/v2/dags
```

Tokens expire. Ask for a new one when a call returns 401, and keep tokens in environment variables, not in files. Share connection details through the private channel, not in issues or PRs.

## Publishing and running the pilot DAG

1. Push the DAG to `src/dags/` on `main` of the pilot repository. `git-sync` picks it up within a minute.
2. Check that `pilot_portability` appears in the DAG list, and that it is not paused.
3. Trigger a run with `items=10000` and `shards=1` and read its state and XCom through the API. The expected final XCom is `333283335000`.

## Checks after a change

- Argo CD shows `airflow` and `airflow-pg` as Synced and Healthy.
- `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor` and both `airflow-pg` Pods are Ready.
- Effective settings: `kubectl -n airflow exec deploy/airflow-scheduler -c scheduler -- airflow config get-value core executor` prints `KubernetesExecutor`, and the Pod image tag is `3.4.0`.
- A task Pod appears during a run and ends in `Completed`.

## Notes

- The chart's database and user jobs are Argo CD sync hooks that delete themselves after they succeed. The first sync can show them running before the database is ready, and retries until it is.
- Resource requests follow the measured use of each component (`kubectl -n airflow top pods --containers`). Re-measure after a change in DAG load and adjust them.
- Removing the Applications does not delete the database volume or the secrets of the namespace.
