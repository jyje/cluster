# Node labels

Korean version: [node-labels-ko.md](node-labels-ko.md)

Node labels are managed by Argo CD through the `node-labels` Application
(`clusters/r4spi/apps/node-labels.yaml`). Do not set them by hand with
`kubectl label`.

## What the labels mean

A label is a `key=value` tag on a node. A workload picks nodes with a
`nodeSelector` (exact match) or a node affinity. All keys use one domain,
`app.jyje.online`:

| Key | Values | Meaning |
| --- | --- | --- |
| `app.jyje.online/node.family` | `raspberry-pi` | Hardware family. |
| `app.jyje.online/raspi.ram` | `8g` | RAM size. |
| `app.jyje.online/raspi.type` | `4b`, `5b` | Pi model: Pi 4 (4 KB pages, slower core) or Pi 5 (faster core). |

Current nodes: `raspi-40` and `raspi-41` are `4b`. `raspi-50` and `raspi-51` are `5b`.

The labels mark hardware classes, not quality. Some software needs one class:
Envoy and Factorio run on `5b` nodes, Envoy cannot map its heap on the 4 KB page
nodes, and qdrant is pinned to `4b`.

## How it is managed

- Each node has a `Node` manifest with only its name and its `app.jyje.*` labels,
  rendered by the `manifest-group` chart. Labels set by the kubelet and other
  controllers are not declared.
- Server-side apply makes Argo CD own only the declared keys.
- Every Node carries `argocd.argoproj.io/sync-options: Prune=false,Delete=false`,
  so Argo CD never prunes or deletes a Node, even if the Application is removed.
- The Application has no automatic sync. After a merge, sync `apps` first (the
  labels live in the Application resource), then `node-labels`.

## Change a label

1. Edit the node's `labels` in `clusters/r4spi/apps/node-labels.yaml` and merge.
2. Sync `apps`, then `node-labels`.
3. Removing a key from Git removes it from the node only if Argo CD is the sole
   owner. A key first set with `kubectl label` stays owned by that tool, so
   remove it once by hand: `kubectl label node <name> <key>-`.

## Add or replace a node

Add a `Node` entry with the node's exact name before or right after it joins,
and sync. Remove the entry when a node leaves the cluster for good. A leftover
entry would make Argo CD create an empty Node object for a node that does not
exist.

A node that is removed and joined again keeps working as soon as the next sync
runs, because the labels come from Git. Until then, workloads that select on
them are not scheduled there.

## History

The labels used to be set by hand and were split across two domains
(`app.jyje.live` on the Pi 4 nodes and `app.jyje.online` on the Pi 5 nodes).
They were moved in four steps: declare the labels as they were, add the
`app.jyje.online` keys to every node, move qdrant and the Envoy proxies to those
keys, then remove the `app.jyje.live` keys (the last removal was a one-time
`kubectl label` by hand, as described above). The `app.jyje.live` domain is
retired. `raspi-51`'s `5b` label was added by hand before this migration and is
now part of the declaration.
