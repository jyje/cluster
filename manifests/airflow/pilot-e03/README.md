# E03 Airflow pilot DAGs

The Airflow Application uses Kustomize to manage the existing
`airflow/pilot-e03-dags` ConfigMap. Its original git-sync source continues
to provide the baseline DAG.

The pilot repository is the source for the three supplemental definitions.
Copy `reconcile.py` and `chain.yaml` from its `src/dags/` directory. Build
the pilot's `workflows` Docker target to export the packed TypeScript file
`/opt/airflow/pilot-dags/settlement.min.mjs`.

The Airflow Application mounts three individual files from the ConfigMap.
The existing logs PVC also supplies the staged ARM64 Node.js, Go, and JVM
runtime assets. For a fresh installation, stage those assets from the pilot's
`mixed` image in the runtime directory referenced by the Application before
syncing. Ensure the three file mount points exist in that directory's
`dags/` subdirectory, alongside its handlers. The ConfigMap owns the file
contents exposed to Airflow.

After editing a source file, sync the Application and restart the DAG processor
so its ConfigMap subPath mounts pick up the new content. New task Pods mount
the current content.
