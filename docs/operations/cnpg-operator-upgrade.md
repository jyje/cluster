# CloudNativePG operator and Barman plugin upgrade (0.29.1 and 0.8.1)

Korean version: [cnpg-operator-upgrade-ko.md](cnpg-operator-upgrade-ko.md)

## Overview

| Chart | From | To | Application version |
|-------|------|----|---------------------|
| `cloudnative-pg` | 0.29.0 | 0.29.1 | operator 1.30.0 to 1.30.1 |
| `plugin-barman-cloud` | 0.7.1 | 0.8.1 | plugin v0.14.0 to v0.15.1 |

Both charts keep the repository's `extraResources` patch. It was re-applied by
extracting the previous patch against the previous upstream chart and applying it
to the new one, so the footprint is identical (`PATCH.md`,
`templates/extra-resources.yaml`, a block in `values.yaml`).

## Compatibility

| Question | Answer | Source |
|----------|--------|--------|
| Does the plugin support operator 1.30? | Yes. The plugin needs operator 1.26 or newer | plugin installation docs |
| Does the plugin need cert-manager? | Yes, it is installed | chart README |
| Minimum Kubernetes for the plugin chart | 1.29 | chart `kubeVersion` |
| Breaking rename in "0.8.x"? | That is the plugin application v0.8.0 (2025-10-27), long passed. Chart 0.8.1 is unrelated and the deployment already uses the new names | plugin release v0.8.0 |
| Do the databases pin their PostgreSQL image? | Yes, all four clusters set `imageName`, so the new operator default (18.6) does not apply | live cluster |
| Does any cluster use the Barman plugin? | No (`plugins` is empty on all four) | live cluster |

## What changes

Operator chart:

- Image 1.30.0 to 1.30.1. Fixes include failover that could stall, fenced instances blocking recreation, and a webhook path check.
- New value `scratchData.emptyDir`, default `{}`, equal to the previously hardcoded value.
- CRDs: additive `restoreAdditionalCommandArgs` and description edits. `Pooler` gets `minimum: 0` checks, and no `Pooler` exists.
- RBAC is unchanged.

Plugin chart:

- Image v0.14.0 to v0.15.1 (Barman 3.20).
- New value `logLevel`, default `info`. The old chart hardcoded `debug`, so the plugin log gets quieter. Set `logLevel: debug` to keep the old output.
- One CRD description edit.

## The operator upgrade restarts every PostgreSQL instance

After the operator controller updates, CloudNativePG rolls a new instance manager
into each PostgreSQL pod. The default is a rolling update that ends with a
switchover per cluster, and all clusters roll at once. There are 4 clusters with
3 instances each, and their data shares one NFS-backed USB drive.

This change adds two documented operator settings to spread the rollout:

| Key | Value | Meaning |
|-----|-------|---------|
| `CLUSTERS_ROLLOUT_DELAY` | 120 | seconds between different clusters |
| `INSTANCES_ROLLOUT_DELAY` | 30 | seconds between instances of one cluster |

`ENABLE_INSTANCE_MANAGER_INPLACE_UPDATES` (in-place update without restarts) is
documented too, but it is left off to keep the default behavior.

## Rollout order

1. Merge the cert-manager upgrade first and wait until its issuers are `Ready`. The plugin issues its certificates through cert-manager.
2. Check that all four database clusters report `Cluster in healthy state` with all replicas streaming. A replica stuck in recovery makes the rolling update worse. Re-clone it first if needed.
3. Upgrade the plugin chart alone. No cluster uses it, so it cannot affect data.
4. Upgrade the operator chart alone, off-peak. Expect the two operator pods to roll, then the clusters one after another with a short switchover each.
5. Watch until all clusters are healthy again:

```sh
kubectl get cluster.postgresql.cnpg.io -A -w
```

## Rollback

- Plugin: revert the commit. The plugin holds no state.
- Operator: revert the commit. The CRD changes are additive, so the old operator accepts the objects. The instance manager changes back, so the PostgreSQL pods roll again with the same spacing.
- If a cluster stays unhealthy after a roll, treat it like any stuck replica: look at the pod log first, and re-clone the replica (delete its pod and PVC) only when recovery cannot make progress.

## Tests

| Check | Result |
|-------|--------|
| `helm lint` and `helm template` with the Application values, both charts | Pass |
| Resource list, old vs new (29 and 20 resources) | Identical |
| `extraResources` hook, object and string form, old and new charts | Both forms render and the namespace expression is evaluated |
| `kubectl diff` against the live cluster | Image tags, CRD additions, plugin `info` log level and sidecar image. No RBAC or Service change |
| Operator rolling restart on a disposable cluster | **Not run.** The workstation disk was nearly full and the shared container VM was low on space |
| Operator rolling restart on the live cluster (2026-10-27) | Merged 11:26 UTC. All 12 PostgreSQL pods were on instance manager 1.30.1 and all 4 clusters were healthy at 11:45 UTC, about 19 minutes in total. The delay settings worked: clusters waited (`Cluster upgrade delayed`) and rolled one after another, each ending in a switchover. LiteLLM stayed connected to its database (`db: connected`) and all Argo CD Applications ended `Synced` and `Healthy` |
