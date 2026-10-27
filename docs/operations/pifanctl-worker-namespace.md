# pifanctl: move the workers to their own namespace

Korean version: [pifanctl-worker-namespace-ko.md](pifanctl-worker-namespace-ko.md)

## Why

Hardware workers and temperature agents need hostPath volumes, and only the
`privileged` Pod Security level allows those. Today they run in the same
namespace as the operator, so that namespace cannot be restricted. This change
gives the workers and agents a namespace of their own. The operator keeps only
Leases and Events in its own namespace.

This is step 2 of pifanctl issue #91. Step 1 (1.2.2 to 1.5.1 in the same
namespace) is done and verified. Step 2 was applied on 2026-10-27 and verified,
see "What was observed". **Do not repeat a change like this outside a maintenance
window.** While no worker holds a fresh heartbeat the Fan reports
`AwaitingWorker`, and the temperature rises.

## What the change does

| Object | Release namespace `pifanctl` | New `pifanctl-workers` |
|--------|------------------------------|------------------------|
| Namespace, labeled `privileged`, kept if removed from Git | | created |
| Operator Deployment | stays, gets `--worker-namespace pifanctl-workers` | |
| Operator Role | keeps `events` and `leases` only | |
| Role and RoleBinding for Deployments, Pods, ConfigMaps | removed | created |
| Agent DaemonSet, worker Service, agent Service | old objects stay until deleted | created |
| ServiceMonitors, worker NetworkPolicy | old objects stay until deleted | created |
| Hardware worker Deployment | old one stays until deleted | created by the operator |

Argo CD does not prune here (automated sync without prune), so the old objects
stay until they are deleted by hand, and the Application shows `OutOfSync` until
then. The worker Deployments are created by the
operator, so Argo CD does not own them.

## Before the window

1. A maintainer-approved window and an archived copy of the current state outside Git.
2. `Fan` is `Regulating`, `CoolingZone` is `Ready` and every member in `nodeTemperatures` is `Fresh`.
3. Prometheus selects ServiceMonitors from every namespace. This was checked: `serviceMonitorNamespaceSelector` is empty and the selector is `release=prometheus`, which the ServiceMonitors carry.
4. An independent cooling recovery method is in place.

## Procedure

1. Merge the pull request. Argo CD creates the namespace, restarts the operator with the new flag, updates the Roles and creates the new agents, Services, ServiceMonitors and NetworkPolicy.
2. The gap starts when the operator restarts with the new flag, not when you delete the old worker. From then on the Fan reports `AwaitingWorker`. The new worker cannot drive the fan while the old worker holds the host lock, so be ready to run the next command right after the merge.
3. Delete the old hardware worker first, so the lock is released:

```sh
kubectl -n pifanctl get deploy
kubectl -n pifanctl delete deploy <old-worker-deployment>
```

4. The new worker was Ready about 22 seconds after the old one was deleted. Do not assume the fan ran at 100 percent during the gap: the Fan reported no duty and no RPM then, and the temperature rose (see "What was observed").
5. Delete the other old objects in the release namespace by name:

```sh
kubectl -n pifanctl delete ds pifanctl-v1-staging-operator-agent
kubectl -n pifanctl delete svc pifanctl-v1-staging-operator-agent pifanctl-v1-staging-operator-worker
kubectl -n pifanctl delete servicemonitor pifanctl-v1-staging-operator-agent pifanctl-v1-staging-operator-worker
kubectl -n pifanctl delete networkpolicy pifanctl-v1-staging-operator-worker
```

6. Verify, and write down anything not observed as "Not measured":

```sh
kubectl get coolingzone r4spi-rack -o yaml     # nodeTemperatures: Fresh for every member
kubectl get fan                                # Ready, duty falls back to the curve
kubectl -n pifanctl-workers get pods
```

Also check that Prometheus lists the new targets and that the old ones are gone.

## What was observed (applied 2026-10-27, UTC)

| Moment | Observation |
|--------|-------------|
| Pull request merged | 11:51:31 |
| Fan state at the first sample, right before deleting the old worker | `AwaitingWorker`, no duty, no RPM |
| Old worker deleted | about 11:52:58 |
| Fan `Regulating` again | within 27 seconds of the deletion (11:53:25), duty 95 percent |
| Duty afterwards | 55 percent, then 42.7, then 41.3 percent, back on the curve |
| Control temperature | 49.6 °C before, **54.55 °C** at the first `Regulating` sample, 50.15 °C about 35 seconds later |

The gap lasted between roughly 30 and 75 seconds. The temperature rose about 5 °C, which does not look like a fan at 100 percent, but the fan speed during the gap was **not measured**. Plan the window with that in mind and keep an eye on the temperature.

After the move: all four `nodeTemperatures` members `Fresh`, `CoolingZone` Ready and Regulating, the tachometer reading 1014 RPM, Argo CD `Synced` and `Healthy`, and no errors in the operator log.

## Rollback

Revert the pull request. The operator goes back to the release namespace and
creates a worker there. Delete the objects in `pifanctl-workers` afterward. Expect
the same failsafe gap again.

## After the move (separate, later changes)

- Label the release namespace `pod-security.kubernetes.io/enforce: restricted` (for example with `managedNamespaceMetadata`). Do this only after the old workers and agents are gone, or new Pods there are rejected.
- Set `workerAdmission.enabled: true` and confirm the real worker is admitted.
- Optionally set `networkPolicy.workerEgress.enabled: true` on one node first and confirm `nodeTemperatures` stays `Fresh`.

## Tests

| Check | Result |
|-------|--------|
| `helm lint` and `helm template` at the pinned chart commit, current vs new values | Pass |
| Rendered inventory | Agent DaemonSet, Services, ServiceMonitors and NetworkPolicy move to the new namespace. New Role, RoleBinding and Namespace |
| Operator arguments | `--worker-namespace pifanctl-workers` |
| Operator Role in the release namespace | Reduced to `events` and `leases`. The Deployment, Pod and ConfigMap rules move to the worker Role |
| Worker NetworkPolicy ingress | From the release namespace and from `observability` |
| Server-side diff against the live cluster (release namespace and cluster scope) | Three differences only: the operator argument, the reduced Role, the new Namespace |

Verified on the live rack after the move: the ingress rule works on Calico (the
operator reads every agent across namespaces, members are `Fresh`), Prometheus
scrapes five targets in the new namespace and none in the old one, Argo CD
converged without error, and the worker acknowledged across namespaces.

Not measured: the fan speed and PWM duty during the gap. No probe is attached.
