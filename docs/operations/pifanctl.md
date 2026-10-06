# pifanctl: node temperatures and fan control

[English](pifanctl.md) | [한국어](pifanctl-ko.md)

## Overview

[pifanctl](https://github.com/jyje/pifanctl) controls the PWM fan of the
cluster and records the temperature of every node.

| Part | Where | What it does |
| --- | --- | --- |
| `agent` | DaemonSet on every node | Publishes `pifanctl_temperature_celsius{node,zone,type}` |
| `controller` | DaemonSet on the node that has the fan | Drives the fan from the hottest node (`max(pifanctl_temperature_celsius)`) |
| Prometheus | `observability` | Keeps the temperatures (30 days) |
| Dashboard, alerts | Grafana, Prometheus | `Hardware / pifanctl` dashboard and `Pifanctl*` alerts |

It is declared in `clusters/r4spi/apps/pifanctl.yaml` and vendored from the
chart published by the pifanctl repository
(`helm/pifanctl/pifanctl-<version>`).

The controller never relies on one source. Each cycle it uses the higher of the
cluster value and its own node. If Prometheus is unreachable it uses its own
node, and if nothing is readable it runs the fan at full speed. When it stops,
the fan stays at full speed.

## Day-to-day

- **Is the fan following the cluster?** In the dashboard, "Where the controller
  got its temperature" should stay `prometheus`. `local` means it lost
  Prometheus, `failsafe` means it cannot read any sensor.
- **Add a node with a fan.** Add a controller group with its own `nodeSelector`
  to `controllers` in `pifanctl.yaml`. A node must match one group at most. Use
  `driver: sysfs` for a Raspberry Pi 5.
- **Tune the curve.** `controllerDefaults.curve` (or per group): idle below
  `tempLow`, ramp to `dutyMax` at `tempHigh`, and `dutyDownStep` of hysteresis.
- **Upgrade.** Vendor the new chart under `helm/pifanctl/` (see the
  `helm-chart-vendor` skill) and change the path in `pifanctl.yaml`.

## Retention

Prometheus keeps 30 days with a 18 GB size cap (`lgtm-prometheus.yaml`). The
TSDB held about 4 GB for 7 days, so 30 days is roughly 17 GB. The cap sits just
under the 20Gi volume request, so a larger-than-expected TSDB drops its oldest
blocks instead of filling the disk. The agents add a few hundred kilobytes per
month, so the budget is decided by the other workloads. For history beyond 30
days, send the recording rule `pifanctl:node_temperature_max_celsius:max` to a
long-term store.

## Rollout: replacing the hand-applied Deployment

Before this was declared in git, pifanctl ran as a Deployment applied by hand
(`kubectl apply` of the upstream manifest, then edited in place) in the
`pifanctl` namespace. That Deployment is not owned by Argo CD, so Argo CD will
not remove it.

**Why this step is manual.** Argo CD never prunes objects it did not create. The
old Deployment and the new controller would both drive the same fan pin, so the
old one has to go, and a one-time deletion of an object that git never described
cannot be expressed in git.

**Prerequisites** (in this order):

1. The pifanctl pull request is merged, so `ghcr.io/jyje/pifanctl:v<appVersion>`
   exists and the chart is published.
2. The cluster pull request is merged and the `pifanctl` Application has synced.
   Check that the agent pods are running on every node.

**Steps.**

```sh
# 1. Record what is running now, for rollback.
kubectl get deployment pifanctl -n pifanctl -o yaml > pifanctl-legacy-deployment.yaml

# 2. Remove the legacy controller so only one process drives the pin.
kubectl delete deployment pifanctl -n pifanctl

# 3. The new controller (DaemonSet pifanctl-controller-default) takes over.
kubectl get pods -n pifanctl -o wide
kubectl logs -n pifanctl -l app.kubernetes.io/component=controller --tail=20
```

**Verify.** The controller log shows every node's temperature and the node it
follows (marked with `*`), the dashboard has data for every node, and
`pifanctl_fan_duty_percent` is reported:

```
Duty: 86.3%, Temperature: 70.5°C, Following: raspi-51, Source: prometheus, Nodes: raspi-51=70.5* raspi-41=52.1 raspi-50=51.8 raspi-40=49.2
```

**Rollback.** Delete the DaemonSet's controller (set
`controllers.default.enabled: false` in git) and `kubectl apply -f` the file
saved in step 1. The agents can stay.

## Rolled out

Rolled out on 2026-10-01. The hand-applied Deployment was removed after the
`pifanctl` Application synced, and the controller has driven the fan from the
cluster maximum since. Two things only a real board showed:

- **The controller needs root.** The image runs as a non-root user, but
  `RPi.GPIO` maps `/dev/mem`. As a non-root user the controller crash-loops with
  `No access to /dev/mem`. Chart 0.1.2 runs it as root by default.
- **A group's `nodeSelector` is used as written.** Chart 0.1.0 merged it with
  its own default label, which matched no node and left the DaemonSet with no
  pods and no error. Fixed in 0.1.1.

## CI runners (ARC)

The `r4spi-microk8s` runner scale set serves the pifanctl repository. After
upgrading the ARC controller and scale set (0.14.2 to 0.15.0), the
`AutoscalingRunnerSet` was gone and the Application stayed `OutOfSync`, because
the scale set Application has no `selfHeal`. Syncing the Application once
restored it and the listener came back. After any ARC upgrade, check
`kubectl get autoscalingrunnersets -n arc-system`, sync the scale set
Application if it is empty, and run one workflow to see a runner pick it up.

## Pausing for a trial, and recovering

A trial that drives the same fan (for example a new controller from a branch)
must not run next to this one: two controllers on one pin fight over it. Pausing
this release has two traps.

- **Freeze the Application, do not just scale it.** `argocd.argoproj.io/skip-reconcile=true`
  stops Argo CD from touching it, but then it keeps showing `Synced` and
  `Healthy` while nothing is running. Look at the DaemonSets, not at the badge.
- **A key added by hand to a DaemonSet cannot be removed by Argo CD.** A
  `nodeSelector` entry added with `kubectl patch` is owned by another field
  manager, so a sync restores the image but leaves the entry, and the pods stay
  at zero.

**Why recovery is manual.** The paused state and the trial were applied outside
git, so there is nothing in git to converge from. Before undoing anything, look
for another Application that drives the fan
(`kubectl get applications -n argocd | grep -i pifan`, and a privileged pod on
the fan node). Removing the freeze while a trial still runs would start a second
controller on the pin.

**Steps, once the trial is finished or abandoned.**

```sh
# 1. Remove the trial. A hand-made Application has no finalizer, so delete its
#    custom resources first (the operator clears its own finalizers), then the
#    namespace, then its cluster-scoped objects. Leave the Grafana CRDs alone.
kubectl delete application <trial-app> -n argocd
kubectl delete <trial-custom-resources> --all -A
kubectl delete namespace <trial-namespace>
kubectl delete crd <trial-crds>
kubectl delete clusterrole,clusterrolebinding <trial-rbac>

# 2. Unfreeze this release and recreate the DaemonSets from git.
kubectl annotate application pifanctl -n argocd argocd.argoproj.io/skip-reconcile-
kubectl delete ds pifanctl-agent pifanctl-controller-default -n pifanctl
kubectl patch application pifanctl -n argocd --type merge -p '{"operation":{"sync":{}}}'
```

Argo CD does not recreate deleted objects on its own for a revision it has
already synced, hence the explicit sync. The `PrometheusRule` and
`GrafanaDashboard` are shared by name with a trial that reuses this chart, and
the Application reports a `SharedResourceWarning` while both exist; they come
back to this release after the trial is removed.

**Verify.** All agents and the controller are `Running` with the image from git,
the controller log follows the hottest node, `up` is 1 for every `pifanctl-*`
target, and no `Pifanctl*` alert fires.

## Alpha.6 CRD migration acceptance window

The `pifanctl-v1-staging` Application pins operator chart 0.1.0-alpha.6 at
`e04f73b53e52050a31da274723a8d4b2ca8e61a1` and the Python 3.12
compatibility image `ghcr.io/jyje/pifanctl-issue:cbc8958-py312`. Its verified
image digest is
`sha256:774e8355d08ba18bcca660c4045d7dfc8f3ed25e77661c305f97c97ea387f49f`.
The default Python 3.14 image is not substituted during this trial: this
cluster's legacy CA profile requires the verified Python 3.12 client.

Automatic synchronization is temporarily disabled for this Application.
Merging this preparation alone does not start the candidate worker. Preserve
the existing alpha.3 image, Application, CRDs, resource UIDs/specs/finalizers
and runtime snapshot before proceeding. The v0 rollback archive must also
pass its checksum inventory.

1. With the alpha.3 worker still regulating, explicitly apply the dual-version
   CRDs, rewrite every resource to v1, verify the complete inventory, and only
   then clear the alpha storage history. Exercise the reverse rewrite and
   restore the archived alpha-only definitions. Verify the original worker
   UID and uninterrupted healthy telemetry. Do not delete a CRD or finalizer.
2. Promote storage again, then manually synchronize the exact candidate
   Application source. Keep the same operator identity, Node UID and PWM
   channel. Worker replacement uses Recreate and the shared host lock.
3. Verify source-matched Argo success, one worker, fresh four-member telemetry,
   readiness, image identity and requested duty. Exercise the archived image
   rollback through a reviewed GitOps change before returning to the candidate.
4. Restore automation after acceptance, retaining the archives until the
   release decision. Electrical waveform, RPM, hardware failures and target
   temperature stability remain separate release gates.

See the upstream [storage procedure](https://github.com/jyje/pifanctl/blob/main/docs/v1/api-migration.md)
and [acceptance plan](https://github.com/jyje/pifanctl/blob/main/PLAN.md).

### Runtime image rollback trial

During the manual acceptance window, select the archived alpha.3 image
`69a829f-py312` again while retaining the dual-version chart and stable v1
instance manifests. This tests compatibility and the Recreate/shared-lock
return path without deleting CRDs or changing the physical rack topology.
Verify the current source after manual synchronization, one Ready worker,
resource UIDs, fresh direct worker/Prometheus observations and the restored
image. Return to the verified alpha.6 image through a subsequent GitOps change
and restore automatic synchronization after successful verification. This is
a runtime image rollback, not the full v0 topology rollback or electrical
acceptance.
