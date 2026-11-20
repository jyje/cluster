# n8n on the official Helm chart

This page is the working plan for moving the `n8n` Application from the 8gears chart (2.1.1) to the official chart (1.19.0). Tracking issue: #256.

The Application in this change is **not auto-synced**. Merging the change does not start the cutover. You sync by hand after the backup.

## What stays and what changes

| Item | 8gears release | Official chart with this change |
| :-- | :-- | :-- |
| Release identity | `n8n` | `n8n` (`fullnameOverride`) |
| PVC | `n8n`, 10Gi, `subdir-usb` | `n8n`, same size and class. Same object, so the data stays. |
| ConfigMap, ServiceAccount | `n8n` | `n8n` |
| Deployment, Service, Ingress | `n8n` | `n8n-main`. The chart adds `-main` and no value changes it. |
| Pod selector | 8gears labels | official labels. A Deployment selector cannot change in place. |
| Database | SQLite on the volume | SQLite on the volume (`queueMode` off, `database.type: sqlite`) |
| Valkey | deployed | gone |
| Image | `n8nio/n8n:2.6.2` | chart default `2.47.4`. n8n migrates its data on first start. |
| Startup probe | n/a | 300 s fixed upstream. A local patch makes it configurable, and the Application allows 900 s. |
| Host, TLS, Homer annotations | as before | as before |

The Homer card keeps working because the chart's selector label `app.kubernetes.io/name: n8n` is the same.

## Secret

The chart reads four keys from the Secret named by `secretRefs.existingSecret`:

| Key | Value |
| :-- | :-- |
| `N8N_ENCRYPTION_KEY` | the key n8n already uses |
| `N8N_HOST` | `n8n.app.jyje.online` |
| `N8N_PORT` | `5678` |
| `N8N_PROTOCOL` | `https` |

The 8gears release did not set a key, so n8n created one inside the data volume, in `/home/node/.n8n/config` under `encryptionKey`. Copy that value into the Secret. If the Secret holds a different key, saved credentials cannot be decrypted. Do not print the key into logs or commit it. Seal the Secret with the repository's SealedSecret flow.

## Rehearsal (no production effect)

1. Back up the volume. Stop the writer first so the SQLite file is consistent:
   ```bash
   kubectl -n n8n scale deploy/n8n --replicas=0
   kubectl -n n8n run n8n-backup --rm -i --restart=Never --image=busybox \
     --overrides='{"spec":{"containers":[{"name":"b","image":"busybox","command":["sh","-c","cp -a /data /backup/n8n-$(date +%F)"],"volumeMounts":[{"name":"d","mountPath":"/data"},{"name":"b","mountPath":"/backup"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"n8n"}},{"name":"b","persistentVolumeClaim":{"claimName":"<backup-pvc>"}}]}}'
   kubectl -n n8n scale deploy/n8n --replicas=1
   ```
   Replace `<backup-pvc>` with a volume you control. Check that the copy contains `database.sqlite` and `config`.
2. Render the chart with the Application values and compare names:
   ```bash
   yq '.spec.source.helm.valuesObject' clusters/r4spi/apps/n8n.yaml > /tmp/n8n-values.yaml
   helm template n8n helm/n8n-io/n8n-1.20.0 -f /tmp/n8n-values.yaml -n n8n
   ```
3. Try the new chart and image on a copy. Restore the backup into a new PVC in a scratch namespace and install the chart there with `ingress.enabled=false`, `persistence.existingClaim=<restored-pvc>` and the same Secret. Port-forward and check that sign-in, credentials and one workflow work. Block external side effects (disable schedule triggers) while testing.

## Cutover

1. Take the final backup (step 1 above). Keep the old volume untouched as the rollback source.
2. Create the Secret `n8n-encryption` in namespace `n8n`.
3. Merge this change. Nothing syncs yet.
4. In Argo CD, sync `n8n` by hand with **Prune off**. The old Deployment `n8n` and the Valkey objects are not in the new manifest, so they show as out of sync. Delete the old Deployment by hand after the new pod is ready, so only one writer mounts the volume.
5. Check: the Application is Synced and Healthy, the pod is Ready, sign-in works, saved credentials work, one workflow runs, and one webhook answers.
6. After a stable period, remove the leftover 8gears objects, enable automated sync again, and move the Renovate catalog entry to the official source (`helm-sources/catalog.yaml`). That last change cannot come earlier, because the vendor check requires the Application to point at the chart it vendors.

## Rollback

1. Scale `n8n-main` to zero.
2. Restore the old Application (revert this change) and sync. The 8gears release comes back with the same PVC.
3. If n8n already migrated the data to 2.47.4, the old 2.6.2 image may not open it. Restore the pre-cutover backup into the PVC first, and account for any workflow runs that were accepted after the cutover.
