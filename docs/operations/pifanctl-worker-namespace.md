# pifanctl: move the workers to their own namespace

Korean version: [pifanctl-worker-namespace-ko.md](pifanctl-worker-namespace-ko.md)

## Why

Hardware workers and temperature agents need hostPath volumes, and only the
`privileged` Pod Security level allows those. Today they run in the same
namespace as the operator, so that namespace cannot be restricted. This change
gives the workers and agents a namespace of their own. The operator keeps only
Leases and Events in its own namespace.

This is step 2 of pifanctl issue #91. Step 1 (1.2.2 to 1.5.1 in the same
namespace) is done and verified. **Do not merge this change outside a
maintenance window.** The fan follows failsafe duty while no worker holds a fresh
heartbeat.

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
2. The new worker cannot drive the fan while the old worker holds the host lock. Members show `Unavailable` until the new agents report. This does not change failsafe behavior.
3. Delete the old hardware worker first, so the lock is released:

```sh
kubectl -n pifanctl get deploy
kubectl -n pifanctl delete deploy <old-worker-deployment>
```

4. The fan runs at failsafe duty (100 percent) until the new worker has a fresh heartbeat. During the 1.2.2 to 1.5.1 worker replacement this took about 30 seconds, measured by ten-second polling. Treat that as the order of magnitude, not a guarantee.
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

Not tested: the worker NetworkPolicy ingress on the real CNI (Calico enforces
policies), worker acknowledgement across namespaces on a node with working GPIO,
how Argo CD orders objects of two namespaces, and the real length of the failsafe
gap. A disposable-cluster run was not possible because the workstation disk was
nearly full.
