# Renovate in cluster

The [Renovate workflow](../../.github/workflows/renovate.yaml) is scheduled daily at 06:00 KST with a GitHub App
installation token scoped to this repository. [Repository policy](../../renovate.json5) limits ordinary dependency PR creation
to Monday from 06:00 until noon KST, allowing time for GitHub Actions scheduling delays. Renovate can propose
security fixes on any run. Dependabot remains enabled.

## Setup and verification

1. Set the `APP_CLIENT_ID` Actions variable and `APP_PRIVATE_KEY` Actions secret in `jyje/cluster` for `jyje-bot`.
2. Verify Dependency graph and Dependabot alerts in the repository settings. Grant the App `Dependabot alerts: read`
   and accept the permission update on the installation.
3. When switching from the pilot runner, remove `jyje/cluster` from its scheduled targets before enabling the new schedule.
4. Run **renovate** with the default `full` dry run and check that the App can access the alerts endpoint. Inspect the
   JSONL artifact for the `jyje/cluster` scan. The workflow retains the artifact for seven days.

Approve major dependency updates and Ubuntu runner changes in the Dependency Dashboard before Renovate opens PRs.
Major chart releases use their own Dependency Dashboard, named for the chart.

## Native Helm vendoring

The workflow builds a pinned Renovate release with the native manager under `tools/renovate/helm-vendor/`.
The [catalog](../../helm-sources/catalog.yaml) lists official Helm sources and opted-in charts. The manager
reads the newest vendored release, uses Renovate's Helm or OCI lookup, downloads the exact selected version,
applies the canonical `extraResources` patch, and renders the chart with the listed Application values.
Renovate runs on the default branch and opens generated PRs against that branch (`main`).
The Helm PR check verifies the target branch and the additions under one versioned chart directory.
Promotion follows the separate
[Helm vendoring review](../../.claude/skills/helm-chart-vendor/SKILL.md).

## Scheduled and manual Helm scans

The daily run scans every catalog chart and runs ordinary dependency and vulnerability checks in a separate job.
Open **Actions → renovate → Run workflow** on `main` to scan all charts manually or enter a single catalog selector
in **helm-profile**. The current values are:

| Value | Scope |
| --- | --- |
| `all` | Every registered chart (default) |
| `tarampampam/error-pages` | error-pages |
| `bitnami-sealed-secrets/sealed-secrets` | sealed-secrets |

The selector uses the catalog repository key and upstream chart name. Each pair must be unique. Keep each chart's
catalog key stable because Renovate uses it in branch names. GitHub Actions accepts the selector as text, so a
catalog change does not require updating a separate workflow input list.

Start with **full** to inspect the run, or choose **off** to allow branches and PRs. **expected-version** is an
optional exact version for one chart. Leave it blank for Renovate to discover available versions.

Each chart gets a separate CI job and log artifact. A chart that is already current creates no branch or PR.
When Renovate proposes an eligible update, it uses that chart's branch and opens a PR against `main`.
Helm updates can create PRs during any scheduled or manual run, subject to the major-release approval rule. Each scan proposes at most one version per chart. Automatic stale
branch pruning is disabled for this workflow because the parallel jobs share the Renovate branch namespace.

## Bot comparison

Record the author, dependency, manifest, old and proposed versions, first PR time, grouping and CI result.
Record each bot's result before merging a shared update. Group security candidates by advisory as well as
dependency. Treat whole-chart vendoring as a separate `jyje-bot` case.

| Runner | GitHub author | Observed starting point |
| --- | --- | --- |
| GitHub Dependabot | `dependabot[bot]` | [Checkout 4 to 7](https://github.com/jyje/cluster/pull/205) |
| Mend-hosted Renovate | `renovate[bot]` | The [Mend dashboard](https://developer.mend.io/github/jyje/cluster) showed a completed Silent-mode scan at 03:05 KST on November 8, 2026 using 44.220.0. It found five Actions dependencies and three pip dependencies. The dashboard reported zero branch updates. |
| Cluster Renovate | `jyje-bot[bot]` | [error-pages 4.2.7](https://github.com/jyje/cluster/pull/212), a whole-chart PR produced by [GitHub Actions](https://github.com/jyje/cluster/actions/runs/42399110990). The [PR check](https://github.com/jyje/cluster/actions/runs/42399892265/job/128485191426) verified the add-only scope. |

These are three observed cases across different baselines. They do not measure relative PR latency. The same-input
comparison records candidates before any of the competing updates is merged.

The [comparison chart](../../tools/renovate/comparison/helm/Chart.yaml) is a standalone Helm manifest outside the
deployment tree. Dependabot and both Renovate runners can use the same `podinfo` dependency as a version update
input. Treat the hosted runner's detected candidates as scan evidence while it is in Silent mode.
The stock Renovate 44.149.2 lookup on the comparison manifest proposed `podinfo` 6.9.1 to 6.17.0.
