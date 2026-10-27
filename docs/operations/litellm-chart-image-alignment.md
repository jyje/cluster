# LiteLLM chart and proxy image: keep them decoupled for now

Korean version: [litellm-chart-image-alignment-ko.md](litellm-chart-image-alignment-ko.md)

## Update: the image was aligned to v1.103.5

The prerequisites below were met and the image moved to `v1.103.5`, matching the
chart. See "Image upgrade test" for the evidence. The sections after it keep the
reasoning that led to the earlier decoupling.

## Decision (earlier)

- **Upgrade the chart now**, from `1.98.0` to `1.103.5`.
- **Keep the proxy image pinned at `v1.89.4`** on purpose. Upgrading it is a separate change with its own plan, because it migrates the database and the migration is one-way.

The chart and the image are versioned together upstream, but this Application has
overridden the image since before chart `1.98.0`. The chart bump does not change
that. It only brings the templates up to date.

## Why the chart bump is safe with the pinned image

The Application values were rendered with both charts and the same image tag.

| Check | Result |
|-------|--------|
| Resource list | Identical, 11 resources |
| Rendered difference | Only the `helm.sh/chart` and `app.kubernetes.io/version` labels and one blank line |
| Image in the Deployment | `ghcr.io/berriai/litellm:v1.89.4` in both |
| `kubectl diff` against the live cluster | Labels on the `litellm` Deployment and Service. Everything else shows only Argo CD tracking annotations |
| Vendored copy | Identical to the pristine upstream chart. No local patch, the chart has `extraResources` natively |

The Deployment's pod template labels change, so the `litellm` pods roll once
(two replicas, `maxUnavailable: 0`). The version label will read `1.103.5` while
the image is `v1.89.4`. That mismatch is cosmetic and is the visible sign of the
decoupling.

Template changes upstream are small: the environment block moved into a helper
without changing its output, the migration Job gained an optional
`activeDeadlineSeconds`, the master key Secret reuses an existing key through
`lookup` (Argo CD renders without cluster access, and this Application supplies
its own master key Secret), and a metrics Service and a collector option were added.

## Why the image bump is a separate change

Between `v1.89.4` and `v1.103.5` upstream added **57 database migrations** and
removed none. Checked from the migration SQL:

| Kind | Count |
|------|-------|
| `ADD COLUMN` | 40 |
| `CREATE TABLE` | 14 |
| `CREATE INDEX` without `CONCURRENTLY` | 11 |
| `DROP`, `RENAME`, data `UPDATE` or `DELETE` | a few, mostly on `shadow_eval_*` tables created inside the same window |

Most are additive. The risks that remain:

1. Index builds on `SpendLogs`-style tables take locks while they build. The size
   of those tables in this database has **not been measured**.
2. This Application runs with `migrationJob.enabled: false`, so the proxy applies
   migrations itself at startup. During a rolling update the old pods run against
   a migrated schema.
3. The database is forward-only. There is no backup through an object store.

The release notes list no explicit breaking change for stable releases in this
range, but they are generated pull request lists, so that is weak evidence.

## Before the image bump

1. Measure the largest table sizes and row estimates in the `litellm` database.
2. Take a logical dump (`pg_dump`) and prove it restores into a scratch database.
3. Prefer a dedicated migration run: enable `migrationJob` for the upgrade and keep
   the default `activeDeadlineSeconds: 1800`, or run one replica during the roll.
4. Read the notes of every stable release in range for configuration keys used in
   `proxy_config` and `litellm_settings`.
5. Pick a quiet window. Hermes Agent calls this proxy inside the cluster and keeps its own copy of the context numbers, so check that copy against `model_info` after any model change.

## Smoke test plan (after any image change)

1. `kubectl rollout status deploy/litellm` finishes and both pods are Ready.
2. `/health/readiness` and `/health/liveliness` return 200.
3. `/v1/models` lists every `model_name` in `model_list`.
4. `/model/info` shows `max_input_tokens` for the entries that define it.
5. One chat completion per provider path: NVIDIA NIM, Upstage, and the image and embedding models.
6. The UI login works and the virtual keys page loads. Create a test key and delete it.
7. After a completion, a row appears in the spend logs.
8. Hermes Agent can still reach the proxy.
9. The pod logs show no migration or Prisma errors. All rows in `_prisma_migrations` are finished.

## Image upgrade test (2026-10-27)

The production database was dumped and restored into a throwaway PostgreSQL 18
container. LiteLLM `v1.103.5` then ran against that copy with the live
`config.yaml`, and `v1.89.4` ran against both the original and the migrated copy.

| Question | Result |
|----------|--------|
| Size of the database | 17 MB in total. The largest table, the spend logs, has about 1,200 rows and 4 MB, so index builds cannot hold a lock for long |
| Does the dump restore completely? | Yes. `pg_restore --exit-on-error` succeeded and every table row count equals production |
| Do the 57 migrations apply? | Yes, in about a second. 186 applied, 0 unfinished, 0 rolled back |
| Is any existing data lost? | No. Row counts of all tables that existed are identical |
| Does the new image work on that data? | Yes. 15 models, `max_input_tokens` preserved, three completions, key generate and delete, spend log write |
| Can an old pod run on the migrated schema (rolling update)? | Yes. `v1.89.4` reports no pending migration, is healthy, serves models and completions and creates keys |
| Config key warnings in the startup log | None for either image |
| Startup time | About 205 to 220 seconds locally for both images, because the Copilot model waits for a device authorization. The probe budget is 300 seconds. Production mounts a token, so it is faster there |

`migrationJob` stays disabled. The migrations took about a second and the old pods
keep working on the new schema, so a dedicated Job adds nothing here.

## Rollback

- Chart: revert the commit. Nothing stateful changes.
- Image: only before the first new pod starts migrating. After that, restore the
  dump taken just before the upgrade and set the tag back. The restore was tested.

## A newer chart exists

While preparing this, the registry already offered chart `1.106.4`. This change
follows the target in the issue (`1.103.5`). The same render comparison can be
repeated for a later chart.
