# Gateway API CRD upgrade (1.2.1 to 1.6.3)

Korean version: [gateway-api-crd-upgrade-ko.md](gateway-api-crd-upgrade-ko.md)

## Overview

The `gateway-api` Application installs the standard-channel Gateway API CRDs
through a small wrapper chart under `helm/gateway-api/`. The wrapper holds the
upstream `standard-install.yaml` release manifest unchanged, plus this
repository's `extraResources` hook.

| Item | 1.2.1 | 1.6.3 |
|------|-------|-------|
| CRDs | 5 | 10 |
| New CRDs | | `BackendTLSPolicy`, `ListenerSet`, `TCPRoute`, `TLSRoute`, `UDPRoute` |
| Other objects | none | `ValidatingAdmissionPolicy` and binding `safe-upgrades.gateway.networking.k8s.io` |
| Storage versions of the existing 5 | `v1` (`ReferenceGrant`: `v1beta1`) | unchanged |

`ReferenceGrant` also serves `v1` from 1.6.3 while its storage version stays
`v1beta1`, so no stored-version migration is needed.

## What the safe-upgrades policy does

The bundle ships an admission policy that denies two things for CRDs in the
`gateway.networking.k8s.io` group:

1. Installing experimental-channel CRDs over standard-channel CRDs.
2. Installing a CRD bundle older than v1.5.0.

The second rule matters for rollback. After the upgrade, simply reverting the
commit and letting Argo CD re-apply 1.2.1 is refused.

## Rollback

Run on a machine with cluster access, then revert the commit:

```sh
kubectl delete validatingadmissionpolicybinding safe-upgrades.gateway.networking.k8s.io
```

Argo CD then applies 1.2.1 without errors. The five new CRDs stay installed
(automated sync does not prune) and are harmless. Syncing 1.6.3 again recreates
the binding.

## Tests

The upgrade, rollback and re-upgrade were run on disposable kind clusters
(Kubernetes v1.36.4 and v1.37.0) with server-side apply and the same field
manager as Argo CD. The cluster held the three live `GatewayClass` objects and a
sample `Gateway`, `HTTPRoute` and `ReferenceGrant`.

| Check | Result |
|-------|--------|
| Upgrade 1.2.1 to 1.6.3 | Succeeds, all 10 CRDs at bundle v1.6.3 |
| Objects before and after | All specs identical |
| Existing kinds through `v1beta1` and the new `ReferenceGrant` `v1` | Readable |
| Second identical apply | No change (`resourceVersion` stays) |
| Re-apply 1.2.1 with the policy installed | Denied |
| Delete the binding, re-apply 1.2.1 | Succeeds, objects identical |
| Upgrade again after rollback | Succeeds, binding returns |
| Experimental CRD over standard | Denied |

The live API server also accepted the rendered bundle in a server-side dry run.

## Controllers

At the time of the upgrade no Gateway API controller runs: there are no
`Gateway` or route objects, and the three `GatewayClass` objects are leftovers
of Istio, which is currently disabled. Istio 1.30 officially targets Gateway API
v1.5.1. Before enabling Istio again, confirm that the Istio version supports the
installed CRD bundle, or pin the wrapper to the version Istio documents.
