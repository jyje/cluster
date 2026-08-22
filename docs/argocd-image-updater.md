# Argo CD Image Updater

This cluster runs the Argo CD Image Updater controller in the `argocd`
namespace. Its first and only managed workload is the `mungchilog` Argo CD
Application.

The Mungchilog Helm chart owns its `ImageUpdater` CR through
`extraResources`. The CR explicitly uses the `argocd` namespace because the
Argo CD `Application` resource it updates also lives there. This preserves
per-application ownership without enabling Argo CD Applications in arbitrary
workload namespaces.

## Release flow

1. Merge an application change to `jyje/mungchilog` `main`.
2. The `Build and push app image` workflow publishes one immutable public GHCR
   tag in the form `<GitHub run number>-<7-character commit SHA>`, such as
   `22-a1b2c3d`.
3. Image Updater polls GHCR every five minutes, selects the newest tag that
   matches `^[0-9]+-[0-9a-f]{7}$`, and sets `image.tag` directly on the live
   Mungchilog Argo CD Application.
4. Argo CD sees the immutable tag change and deploys it.

`managed` is intentionally a nonexistent Helm sentinel, not a registry tag.
`forceUpdate: true` makes Image Updater replace it with the first matching
workflow tag. Merge the Mungchilog workflow change and wait for its successful
image-push job before merging the cluster change that declares `managed`.

## Deliberate non-Git write-back design

The controller uses `writeBackConfig.method: argocd`, so it needs neither a
GitHub token nor a GitHub App private key. The image is public, so it also needs
no registry pull secret.

The root `apps` Application ignores and preserves only
`/spec/source/helm/parameters` on the Mungchilog child Application. That avoids
the normal app-of-apps self-heal loop from resetting Image Updater's live Helm
parameter. Git keeps `image.tag: managed`; the selected workflow tag remains
cluster state and is observable through the Mungchilog Application and
ImageUpdater status.

The Mungchilog Application currently does not enable automated pruning. If its
`ImageUpdater` entry is removed from `extraResources`, delete the existing CR
explicitly after the Application has synced; it is not pruned automatically.

## Operations

```sh
kubectl -n argocd get imageupdater mungchilog -o yaml
kubectl -n argocd get application mungchilog -o yaml
kubectl -n argocd logs deploy/argocd-image-updater-controller --tail=200
```

To pause automatic image changes, change the `mungchilog` ImageUpdater's
`namePattern` to a value that matches no Application, merge that cluster
configuration, and then restore `mungchilog` when ready. Do not edit the live
Mungchilog Application's generated Helm parameter manually: Image Updater will
reconcile it on its next poll.
