---
name: microk8s-release-watch
description: Weekly, read-only check for new MicroK8s releases and decide whether to start an upgrade. Use when the user asks to check MicroK8s releases or updates, as part of a weekly maintenance review, or before planning a Kubernetes upgrade for the r4spi cluster.
---

# MicroK8s Release Watch

Checks whether a newer MicroK8s is available for this cluster, using two cheap,
unauthenticated, read-only HTTP calls. It never changes the cluster.

## Why two sources

| Source | What it tells you | Limit |
| --- | --- | --- |
| GitHub releases of `canonical/microk8s` | A new **minor** release was announced | One entry per minor (v1.36, v1.37). No patch versions |
| Snap Store channel map | What `snap refresh` can actually install, per track, risk and architecture | None for this purpose |

The Snap Store is the gate. Upstream Kubernetes 1.37 was out weeks before the
MicroK8s 1.37 track existed, so an announcement alone is not a reason to plan
downtime. The script reports both and gives one verdict.

## Run it

```bash
.claude/skills/microk8s-release-watch/check.sh
```

Options: `--current vX.Y.Z` (skip kubectl, for example when the cluster is not
reachable), `--arch arm64|amd64` (default `arm64`), `--context microk8s`.

The script prints versions only. It does not print node names, addresses or
credentials, so the output is safe to paste into a public issue.

## Verdicts and what to do

| Verdict | Meaning | Action |
| --- | --- | --- |
| `UP_TO_DATE` | Nodes run the newest stable patch of the newest track | Nothing |
| `PATCH_AVAILABLE` | A newer patch exists in the current track | Nothing. The snap refresh schedule applies it. Mention it if a restart of services on the fan node matters |
| `NEW_MINOR_ANNOUNCED_NOT_IN_STORE` | GitHub has a new minor, the store has no stable snap for the architecture | Nothing to upgrade. Add a short note to the open upgrade issue, then recheck next week |
| `NEW_MINOR_AVAILABLE` | A newer stable track is installable | Start the upgrade checklist below |
| `UNKNOWN` | A call failed or the cluster is unreachable | Rerun, or pass `--current` |

## Upgrade checklist (only for `NEW_MINOR_AVAILABLE`)

Do not run `snap refresh` to a new track from this skill. Write the plan, get
explicit approval, and track it in a cluster issue. The upgrade issue created
for 1.37 (jyje/cluster#158) is the template.

1. Read the final Kubernetes and MicroK8s release notes. Look for removed APIs,
   changed defaults and removed addons.
2. Re-run the read-only checks recorded in the upgrade issue: cgroup version on
   every node, static pods that reference Secrets or ConfigMaps, kube-proxy mode,
   deprecated API requests, PodDisruptionBudgets and database replica placement.
3. Check chart and operator compatibility: Argo CD, cert-manager, ingress-nginx,
   CloudNativePG, Istio ambient, MetalLB, Gateway API and the Prometheus stack.
4. Confirm the preconditions: all Applications Synced and Healthy, all nodes Ready,
   a fresh backup of the certificate and credential directories outside Git, and a
   maintenance window.
5. The node that drives the shared fan also hosts pifanctl's worker. Keep an
   independent cooling recovery method ready and upgrade that node last or with
   extra care. See docs/operations/pifanctl.md.
6. Upgrade one node at a time: drain, refresh the snap channel, uncordon, verify
   Ready, Application health and database replicas before the next node.
7. Re-verify strict TLS and pifanctl. See docs/operations/cluster-ca-key-usage.md
   for what a malformed CA looks like.

## Rules

- Read-only by default. Never change the snap channel, drain a node or restart
  services without explicit approval in the current conversation.
- Patch updates inside a track arrive automatically through the snap refresh
  schedule. Moving to a new minor only happens when the channel is changed on
  purpose.
- Keep notes short and public-safe: versions and dates only.

## Weekly use

Run the script once a week, for example at the start of a maintenance review.
If the verdict is not `UP_TO_DATE`, summarize it in one or two lines and follow
the table above. To automate it, schedule a recurring task that runs this check
and reports the verdict, but keep every action behind approval.

## Offline testing

`MICROK8S_RELEASES_JSON` and `MICROK8S_STORE_JSON` can point to saved API
responses to exercise every verdict without the network.
