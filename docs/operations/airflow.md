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

The two Applications are separate on purpose: the database has its own lifecycle, and each workload keeps its own file.

## Secrets

No secret value is in git in plain text. Six SealedSecrets hold them:

| Secret | Used for |
| :-- | :-- |
| `airflow-pg-creds` | owner of the `airflow` database (CloudNativePG initdb) |
| `airflow-metadata` | the SQLAlchemy connection string (same password as above) |
| `airflow-fernet` | Fernet key for stored connections and variables |
| `airflow-api-secret` | API secret key |
| `airflow-jwt` | JWT signing secret, stable across restarts and replicas |
| `airflow-admin` | password of the `admin` user |

Read the admin password from the cluster, never from git:

```bash
kubectl -n airflow get secret airflow-admin -o jsonpath='{.data.password}' | base64 -d
```

Rotating a value means sealing a new Secret with the same name and namespace and replacing its entry in the Application. Rotating the JWT secret signs every user out. Rotating the Fernet key needs `airflow rotate-fernet-key`, or stored connections can no longer be read.

## Using the API

Airflow 3 has an authenticated public API. A client first gets a short lived JWT, then sends it as a bearer token.

```bash
TOKEN=$(curl -s -X POST https://airflow.app.jyje.online/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<password>"}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" https://airflow.app.jyje.online/api/v2/dags
```

Tokens expire. Ask for a new one when a call returns 401, and keep tokens in environment variables, not in files. The `admin` user is for people. A separate user for the pilot with only the permissions it needs is a follow-up step. Share connection details through the private channel, not in issues or PRs.

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
- Resource requests are small because the nodes are fairly full. Measure after the first runs and adjust.
- Removing the Applications does not delete the database volume or the secrets of the namespace.
