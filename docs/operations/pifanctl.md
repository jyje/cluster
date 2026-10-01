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

**Verify.** The controller log shows `Source: prometheus`, the dashboard has
data for every node, and `pifanctl_fan_duty_percent` is reported.

**Rollback.** Delete the DaemonSet's controller (set
`controllers.default.enabled: false` in git) and `kubectl apply -f` the file
saved in step 1. The agents can stay.
