# Apache Airflow runbook

[한국어](airflow-ko.md)

Airflow 3.4.0 runs on the official Helm chart 1.22.0 with the `KubernetesExecutor`. It is the external endpoint of the [pilot-airflow-portability](https://github.com/jyje/pilot-airflow-portability) project. Rollout issue: #407.

Contents: [Overview](#overview) · [Rollout](#rollout) · [Secrets](#secrets) · [Network](#network-and-certificate) · [Access](#sign-in-users-and-roles) · [API](#using-the-api) · [DAGs](#dags) · [Operations](#operations) · [Troubleshooting](#troubleshooting) · [History](#history)

## Overview

| Part | Choice |
| :-- | :-- |
| Namespace, Argo CD project | `airflow`, `ai` |
| Chart | `helm/airflow/airflow-1.22.0` (official, one local patch: the standard `extraResources` key) |
| Image | `apache/airflow:3.4.0` (the chart default is 3.2.2, so the Application pins it) |
| Executor | `KubernetesExecutor`: one task, one Pod. No Redis, Celery workers, Flower or statsd. The triggerer is off. |
| Components | api-server, scheduler and dag-processor, one replica each |
| Metadata database | CloudNativePG cluster `airflow-pg` (2 instances), Application `airflow-pg` |
| DAGs | two bundles, see [DAGs](#dags) |
| Task logs | shared volume `subdir-usb` (2Gi), because task Pods are short lived |
| Endpoint | `https://airflow.app.jyje.online` (Higress, Let's Encrypt, route limit 20 requests per second) |
| Sign-in | authentik (OpenID Connect), plus local users for API clients |

| File | Content |
| :-- | :-- |
| `clusters/r4spi/apps/airflow.yaml` | Application `airflow`: chart values and SealedSecrets. It has two sources, the chart and `manifests/airflow/pilot-e03` |
| `clusters/r4spi/apps/airflow-pg.yaml` | Application `airflow-pg`: the database cluster and its owner secret |
| `clusters/r4spi/apps/authentik.yaml` | the sealed sign-in blueprint `authentik-airflow-oidc` |
| `clusters/r4spi/apps/homer-instance.yaml` | the dashboard card, see [homer.md](homer.md) |
| `helm-sources/catalog.yaml` | the Renovate entry for the chart |

The two Applications are separate on purpose: the database has its own lifecycle, and each workload keeps its own file.

## Rollout

A chart upgrade follows the steps in [AGENTS.md](../../AGENTS.md): a tracking issue, a vendoring PR, then a deploy PR.

After merging a change:

1. Sync `apps` first. The Helm values live inside the Application, so the child Application would otherwise use the old values.
2. Sync `airflow-pg` when the database changed, then `airflow`. Both sync automatically.
3. Check the [list below](#checks-after-a-change).

The database and user jobs of the chart are Argo CD sync hooks that delete themselves after they succeed.

On the first install, expect it to take a while. Images are pulled once, and `initdb` and the replica join are slow on this storage. The migration job retries until the database is up. If one component stays in a long back-off after the database is ready, delete that Pod and let the Deployment create a new one.

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
| `airflow-pilot` | password of the limited `pilot` user |
| `airflow-oidc` | OAuth client secret for authentik sign-in |
| `authentik-airflow-oidc` | (in the authentik Application) the sealed blueprint with the same client secret |

Read a password from the cluster, never from git:

```bash
kubectl -n airflow get secret airflow-admin -o jsonpath='{.data.password}' | base64 -d
```

Sealing a new value means a new Secret with the same name and namespace and a new entry in the Application (see [introduction.md](../introduction.md#secrets)).

| Rotation | What else to do |
| :-- | :-- |
| OAuth client secret | reseal `airflow-oidc` and `authentik-airflow-oidc` with the same value, in one change |
| JWT signing secret | every user is signed out |
| Fernet key | run `airflow rotate-fernet-key`, or stored connections can no longer be read |
| `admin` or `pilot` password | the user job does not change an existing user. After the new Secret is in the cluster, run `airflow users reset-password` in the api-server Pod |

## Network and certificate

The host needs a CNAME record at the DNS provider, like the other `app` hosts. DNS is not managed from this repository, so this is a manual step. Until the name resolves, cert-manager cannot finish the HTTP-01 challenge: the Certificate stays `False` and the Challenge reports `no such host`. Add the record, and the certificate is issued within a minute or two.

The Ingress allows the dashboard origin (CORS), because the Homer card checks `/api/v2/monitor/health` from the browser.

## Sign-in, users and roles

### People: authentik

People sign in through authentik. The application `airflow` is created by the sealed blueprint `authentik-airflow-oidc` and is bound to `AuthentikAdmin` (which also admits `ClusterAdmin`). Airflow reads the `groups` claim of the ID token and maps it to a role in `apiServerConfig` of the Application:

| authentik group | Airflow role |
| :-- | :-- |
| `AuthentikAdmin` | `Admin` |
| `ClusterAdmin` | `Admin` |

No person is named in git. To make someone an Airflow admin, add their authentik account to `AuthentikAdmin` (see [authentik-access.md](authentik-access.md)). Roles are synced at every login, so removing the group removes the role at the next sign-in. Everyone also gets the default `Public` role, which grants nothing.

The redirect URI is `https://airflow.app.jyje.online/auth/oauth-authorized/authentik`.

### Local users

| User | Role | For |
| :-- | :-- | :-- |
| `admin` | `Admin` | fallback and administration through the API |
| `pilot` | `PilotRunner` | the pilot client |

The job `createUserJob` in the Application creates both users and the role `PilotRunner` on every sync. It is idempotent and never changes an existing user.

`PilotRunner` permissions:

| Resource | Actions |
| :-- | :-- |
| `DAG:pilot_portability` | read, edit (edit is needed to trigger a run) |
| `DAG Runs` | create, read |
| `Task Instances` | read |
| `XComs` | read |

It cannot see other DAGs, delete anything, change task states, read DAG code or task logs, or read connections, variables, configuration or pools. This was checked against Airflow's own authorization code. The e03 DAGs are not included. To give the pilot another DAG, add a line `-r "DAG:<dag_id>" -a can_read can_edit` to the job. Removing a line does not remove the permission, so use `airflow roles del-perms` for that.

### Checking the pilot user

The script signs in as `pilot`, runs the DAG once, reads the result and checks that other calls are refused. It prints no password or token.

```bash
python3 docs/operations/examples/verify-airflow-pilot.py
```

The expected last line is `failures: 0`.

## Using the API

A client first gets a JWT from `/auth/token`, then sends it as a bearer token. A token from `/auth/token` lives 24 hours (`api_auth.jwt_expiration_time`, 86400). The CLI token lives 1 hour (`jwt_cli_expiration_time`, 3600). Both are the defaults.

```bash
TOKEN=$(curl -s -X POST https://airflow.app.jyje.online/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"pilot","password":"<password>"}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" https://airflow.app.jyje.online/api/v2/dags
```

Ask for a new token when a call returns 401. Keep tokens in environment variables, not in files. Share connection details through a private channel, not in issues or PRs.

## DAGs

| Bundle | Source | DAGs |
| :-- | :-- | :-- |
| `dags-folder` | `git-sync` from the pilot repository, `src/dags`, branch `main`, every 60 seconds | `pilot_portability` |
| `pilot-e03` | ConfigMap `pilot-e03-dags` from `manifests/airflow/pilot-e03`, mounted into the dag-processor and the task Pods. A runtime directory comes from the logs volume | `pilot_reconcile`, `pilot_ts_settlement`, `pilot_mixed_language_chain` |

To publish a DAG in `dags-folder`, push it to `src/dags/` on `main` of the pilot repository. It appears within a few minutes (`git-sync` every 60 seconds, then the parser).

To run the pilot DAG, trigger `pilot_portability` with `items=10000` and `shards=1` and read its state and XCom through the API. The expected final XCom is `333283335000`.

Two points about the `pilot-e03` bundle, from [its README](../../manifests/airflow/pilot-e03/README.md):

- On a fresh installation, stage the ARM64 Node.js, Go and Java runtime files and the three file mount points in the runtime directory on the logs volume **before** syncing. They are not in git.
- After editing one of its source files, sync the Application and restart the dag-processor, because the files are mounted with `subPath` and do not update in place. New task Pods see the new content.

## Operations

### Checks after a change

- Argo CD shows `airflow` and `airflow-pg` as Synced and Healthy.
- `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor` and both `airflow-pg` Pods are Ready.
- `kubectl -n airflow exec deploy/airflow-scheduler -c scheduler -- airflow config get-value core executor` prints `KubernetesExecutor`, and the Pod image tag is `3.4.0`.
- `kubectl -n airflow exec deploy/airflow-scheduler -c scheduler -- airflow dags list-import-errors` shows nothing.
- A task Pod appears during a run and ends in `Completed`.

### Resources

Requests follow the measured use of each component (`kubectl -n airflow top pods --containers`). Measure again after a change in DAG load and adjust them.

### Startup

The api-server syncs role permissions into the database before it listens, so its startup probe allows 5 minutes (`startupProbe.failureThreshold: 30`).

### Removal

Removing the Applications does not delete the database volume or the secrets of the namespace.

## Troubleshooting

| Symptom | Cause and action |
| :-- | :-- |
| Certificate stays `False`, Challenge says `no such host` | the DNS record is missing, see [Network](#network-and-certificate) |
| api-server restarts in a loop, `Startup probe failed` | startup is slower than the probe. Check the database first, then raise `failureThreshold` |
| Pods fail in `wait-for-airflow-migrations` with `Connection refused` | the database is not ready. Check `kubectl -n airflow get clusters.postgresql.cnpg.io` and the migration job |
| A component stays in back-off after the database is ready | delete the Pod |
| Sign-in fails at authentik | check the provider (grant types, redirect URI) and the application binding |
| Signed in, but no menus | the account is in neither `AuthentikAdmin` nor `ClusterAdmin` |
| API call returns 401 | the token expired, or the password changed |
| API call returns 403 for `pilot` | expected outside the permissions above |
| A new DAG does not show up | check `git-sync` logs in the dag-processor Pod and `airflow dags list-import-errors` |
| Homer card shows offline | the root page answers HEAD with 405. The card must ping `/api/v2/monitor/health` with GET, and the Ingress must allow the dashboard origin |

## History

| Change | PR |
| :-- | :-- |
| Vendor chart 1.22.0 with the `extraResources` patch | #406 |
| Deploy Airflow 3.4.0, the database and the Renovate entry | #408 |
| Sign-in through authentik, measured memory requests | #413 |
| Longer startup probe for the api-server | #414 |
| Dashboard card and health check | #419, #421 |
| e03 DAG bundle through GitOps and startup timeouts | #423, #425, #426 |
