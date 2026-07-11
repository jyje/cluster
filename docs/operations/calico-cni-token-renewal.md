# Calico CNI ServiceAccount Token Renewal

## Overview

Calico's CNI plugin binary (invoked directly by the container runtime at pod
sandbox creation time, outside the normal pod lifecycle) authenticates to the
Kubernetes API using a static kubeconfig file written to the host filesystem.
That kubeconfig embeds a **bound ServiceAccount token** for the
`calico-node` service account, issued with a short, fixed lifetime (commonly
24 hours, controlled by whatever generated the token).

Unlike tokens mounted into running pods via the `serviceAccountToken`
projected volume (which kubelet auto-refreshes before expiry), this
host-level file is only rewritten when the `calico-node` pod's `install-cni`
init container reruns — i.e., when the pod itself restarts. If nothing
restarts `calico-node` within the token's lifetime, the file goes stale and
**every new pod sandbox creation on that node starts failing** with an error
resembling:

```
Failed to create pod sandbox: rpc error: code = Unknown desc = failed to
setup network for sandbox "...": plugin type="calico" failed (add): error
getting ClusterInformation: connection is unauthorized: Unauthorized
```

| Item | Value |
|------|-------|
| Component | Calico CNI plugin (`calico-node` DaemonSet) |
| Symptom | New pods stuck in `ContainerCreating`; existing pods unaffected |
| Root cause | Static CNI kubeconfig token expires with no renewal mechanism |
| Token subject | `system:serviceaccount:kube-system:calico-node` |

---

## Diagnosis

1. Confirm the failure is CNI-specific, not just one workload's problem —
   check for the same `FailedCreatePodSandBox` / `Unauthorized` event across
   *multiple, unrelated* namespaces. If it is scoped to one node, that node's
   token has likely expired; if it spans all nodes, suspect the same root
   cause but note new pods elsewhere may be masking it if they happen to land
   on a still-valid node.
2. Locate the CNI kubeconfig (path varies by distribution; for MicroK8s it is
   under `/var/snap/microk8s/current/args/cni-network/calico-kubeconfig`) and
   decode the JWT `token:` field's `exp` claim to confirm it has actually
   expired — don't assume from the error message alone.
3. Existing, already-running pods keep working fine even after the token
   expires, since their network plumbing was already set up. This makes the
   problem easy to miss until something needs to schedule a new pod (a
   rolling update, a restart, a scale-up).

## Fix

Restarting the `calico-node` pod on the affected node re-runs its
`install-cni` init container, which requests and writes a fresh token:

```
kubectl delete pod -n kube-system -l k8s-app=calico-node \
  --field-selector spec.nodeName=<node>
```

The DaemonSet controller immediately recreates it. Expect a few seconds to
tens of seconds of network interruption on that one node while the pod
restarts — acceptable for a scheduled maintenance action, not something to
do reactively under load without confirming the node isn't hosting anything
that can't tolerate a brief hiccup (e.g., check for database primaries or
other singleton workloads pinned to that node first).

## Preventing recurrence

There is no built-in automatic renewal for this specific credential in a
plain MicroK8s + Calico setup, so treat it the same as any other
short-lived-credential rotation problem: **schedule the restart before the
token can expire**, with enough safety margin to tolerate a missed run.

A simple, dependency-free approach: one `systemd` timer per node (or
targeting each node from a control-plane host that already has cluster
admin access), running the delete command above on a recurring schedule well
inside the token's lifetime — e.g., twice a day for a 24h token, so a single
missed run still leaves margin. Stagger the schedule across nodes by a few
minutes each so the whole cluster doesn't take a simultaneous, brief
networking blip.

This is a workaround, not a permanent fix — if a future Calico/MicroK8s
release starts refreshing this file automatically, this scheduled restart
becomes redundant (harmless, but worth revisiting).
