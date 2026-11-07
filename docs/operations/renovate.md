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

## Vendored Helm charts

The [error-pages catalog entry](../../helm-sources/error-pages.json) tracks the newest vendored version of the
OCI chart. Renovate reads this entry and runs `ruby scripts/vendor-helm-chart.rb` after updating its version.
The script downloads the exact chart, adds the resource injection patch if needed, and validates the chart before
adding a versioned directory under `helm/error-pages/`. Existing versions stay in Git. Renovate still excludes
`helm/**` from dependency extraction.

To reproduce the vendor operation locally, set the target version in the catalog and run the script from the
repository root with Helm and Ruby installed. `ruby scripts/vendor-helm-chart.rb --check` verifies the catalog and
chart against the Application values without downloading anything. Review the values and dependency summary in the
**Verify Helm vendoring** workflow before merging a chart PR.

Promotion is a separate PR. Follow the [Helm vendoring rules](../../.claude/skills/helm-chart-vendor/SKILL.md) to
review the chart changes, obtain approval, and update the Application path and any applicable floating image tags.
