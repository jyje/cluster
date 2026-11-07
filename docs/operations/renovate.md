# Renovate in cluster

The [Renovate workflow](../../.github/workflows/renovate.yaml) is scheduled daily at 06:00 KST with a GitHub App
installation token scoped to this repository. [Repository policy](../../renovate.json5) limits regular PR creation
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

## Native Helm vendoring

The workflow builds a pinned Renovate release with the native manager under `tools/renovate/helm-vendor/`.
The [catalog](../../helm-sources/catalog.yaml) lists official Helm sources and opted-in charts. The manager
reads the newest vendored release, uses Renovate's Helm or OCI lookup, downloads the exact selected version,
applies the canonical `extraResources` patch, and renders the chart with the listed Application values.
The generated PR adds one versioned chart directory. Promotion follows the separate
[Helm vendoring review](../../.claude/skills/helm-chart-vendor/SKILL.md).

## Bot comparison

Record the author, dependency, manifest, old and proposed versions, first PR time, grouping and CI result.
Record each bot's result before merging a shared update. Group security candidates by advisory as well as
dependency. Treat whole-chart vendoring as a separate `jyje-bot` case.

| Runner | GitHub author | Observed starting point |
| --- | --- | --- |
| GitHub Dependabot | `dependabot[bot]` | [Checkout 4 to 7](https://github.com/jyje/cluster/pull/205) |
| Mend-hosted Renovate | `renovate[bot]` | Hosted execution and PR evidence are collected separately. |
| Cluster Renovate | `jyje-bot[bot]` | [error-pages 4.2.7](https://github.com/jyje/cluster/pull/212), a whole-chart PR produced by [GitHub Actions](https://github.com/jyje/cluster/actions/runs/42399110990). |
