# lgtm-collection

Umbrella chart for LGTM stack (Loki, Grafana, Tempo, Mimir) and supporting storage/DB (SeaweedFS, optional PostgreSQL). Official Grafana, SeaweedFS, CloudNative-PG only; no Bitnami or commercial licenses.

## Operator and instance split

Storage and database components are split into **operator** and **instance** so operators can be managed separately (e.g. cluster-wide CNPG operator).

| Component    | Type     | Values key              | Role |
|--------------|----------|--------------------------|------|
| Grafana      | —        | `grafana`                | UI and dashboards |
| Loki         | —        | `loki`                   | Logs |
| Tempo        | —        | `tempo`                  | Traces |
| Mimir        | —        | `mimir`                  | Metrics (Prometheus) |
| SeaweedFS    | instance | `seaweedfs-instance`     | S3 object storage (no operator) |
| PostgreSQL   | operator | `postgresql-operator`    | CNPG operator (optional; deploy here or elsewhere) |
| PostgreSQL   | instance | `postgresql-instance`    | PostgreSQL cluster (Cluster CR) |
| Garnet       | instance | `garnet-instance`       | Redis-compatible cache (no operator); [official chart](https://github.com/microsoft/garnet/tree/main/charts/garnet) vendored |

Grafana is pre-wired to Loki, Tempo, and Mimir (trace-to-logs, trace-to-metrics). S3 endpoint: when using a release name, override to `<release>-seaweedfs-instance-s3:8333`. PostgreSQL primary: `<release>-postgresql-instance-rw`. Garnet: `<release>-garnet-instance:6379`.

## Install

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add seaweedfs https://seaweedfs.github.io/seaweedfs/helm
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm dependency update
helm install lgtm-collection . -n observability --create-namespace
```

PostgreSQL instance requires the CNPG operator: either set `postgresql-operator.enabled: true` or install it separately (e.g. `helm/cnpg/cloudnative-pg`).

## Configuration

## Values

<table>
	<thead>
		<th>Key</th>
		<th>Type</th>
		<th>Default</th>
		<th>Description</th>
	</thead>
	<tbody>
		<tr>
			<td>grafana</td>
			<td>object</td>
			<td><code>see values.yaml</code></td>
			<td>Grafana: UI and dashboards. When postgresql-instance.enabled, set database type=postgres, host=<release>-postgresql-instance-rw.</td>
		</tr>
		<tr>
			<td>mimir</td>
			<td>object</td>
			<td><code>see values.yaml</code></td>
			<td>Mimir (Prometheus): metrics. Object storage via SeaweedFS S3.</td>
		</tr>
		<tr>
			<td>tempo</td>
			<td>object</td>
			<td><code>see values.yaml</code></td>
			<td>Tempo: traces. Object storage via SeaweedFS S3.</td>
		</tr>
		<tr>
			<td>loki</td>
			<td>object</td>
			<td><code>see values.yaml</code></td>
			<td>Loki: logs. Single binary or scalable; object storage via SeaweedFS S3.</td>
		</tr>
		<tr>
			<td>seaweedfs-instance.enabled</td>
			<td>bool</td>
			<td><code>`true`</code></td>
			<td>Enable SeaweedFS (master, filer, volume, S3 gateway).</td>
		</tr>
		<tr>
			<td>seaweedfs-instance.fullnameOverride</td>
			<td>string</td>
			<td><code>`"seaweedfs-instance"`</code></td>
			<td>Fix the service name so S3 endpoint is always `seaweedfs-instance-s3:8333` regardless of Helm release name. Mimir/Tempo/Loki storage configs are plain strings (not tpl-processed), so they cannot use .Release.Name.</td>
		</tr>
		<tr>
			<td>seaweedfs-instance.endpoint</td>
			<td>string</td>
			<td><code>`"seaweedfs-instance-s3:8333"`</code></td>
			<td>S3 API endpoint. Matches the fixed service name set by fullnameOverride above.</td>
		</tr>
		<tr>
			<td>seaweedfs-instance.pathStyle</td>
			<td>bool</td>
			<td><code>`true`</code></td>
			<td>Use path-style bucket URLs.</td>
		</tr>
		<tr>
			<td>seaweedfs-instance.insecure</td>
			<td>bool</td>
			<td><code>`true`</code></td>
			<td>Skip TLS verification for S3.</td>
		</tr>
		<tr>
			<td>seaweedfs-instance.accessKeyId</td>
			<td>string</td>
			<td><code>`""`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.secretAccessKey</td>
			<td>string</td>
			<td><code>`""`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.master.replicas</td>
			<td>int</td>
			<td><code>`1`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.master.resources.requests.cpu</td>
			<td>string</td>
			<td><code>`"50m"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.master.resources.requests.memory</td>
			<td>string</td>
			<td><code>`"128Mi"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.filer.replicas</td>
			<td>int</td>
			<td><code>`2`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.filer.resources.requests.cpu</td>
			<td>string</td>
			<td><code>`"50m"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.filer.resources.requests.memory</td>
			<td>string</td>
			<td><code>`"128Mi"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.volume.replicas</td>
			<td>int</td>
			<td><code>`2`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.volume.resources.requests.cpu</td>
			<td>string</td>
			<td><code>`"100m"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.volume.resources.requests.memory</td>
			<td>string</td>
			<td><code>`"256Mi"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.s3.enabled</td>
			<td>bool</td>
			<td><code>`true`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.s3.replicas</td>
			<td>int</td>
			<td><code>`2`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.s3.resources.requests.cpu</td>
			<td>string</td>
			<td><code>`"50m"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>seaweedfs-instance.s3.resources.requests.memory</td>
			<td>string</td>
			<td><code>`"128Mi"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>postgresql-operator.enabled</td>
			<td>bool</td>
			<td><code>`false`</code></td>
			<td>Deploy CloudNative-PG operator with this chart. If false, install operator elsewhere (e.g. helm/cnpg/cloudnative-pg).</td>
		</tr>
		<tr>
			<td>postgresql-instance.enabled</td>
			<td>bool</td>
			<td><code>`true`</code></td>
			<td>Deploy PostgreSQL cluster (Cluster CR). Requires CNPG operator.</td>
		</tr>
		<tr>
			<td>postgresql-instance.cluster.instances</td>
			<td>int</td>
			<td><code>`2`</code></td>
			<td>Number of PostgreSQL instances in the cluster.</td>
		</tr>
		<tr>
			<td>postgresql-instance.cluster.storage.size</td>
			<td>string</td>
			<td><code>`"10Gi"`</code></td>
			<td>PVC size per instance.</td>
		</tr>
		<tr>
			<td>postgresql-instance.cluster.resources.requests.cpu</td>
			<td>string</td>
			<td><code>`"100m"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>postgresql-instance.cluster.resources.requests.memory</td>
			<td>string</td>
			<td><code>`"256Mi"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>postgresql-instance.cluster.resources.limits.memory</td>
			<td>string</td>
			<td><code>`"1Gi"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>postgresql-instance.bootstrap.initdb.database</td>
			<td>string</td>
			<td><code>`"grafana"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>postgresql-instance.databases</td>
			<td>list</td>
			<td><code>see values.yaml</code></td>
			<td>Databases to create (CNPG cluster bootstrap).</td>
		</tr>
		<tr>
			<td>garnet-instance.enabled</td>
			<td>bool</td>
			<td><code>`true`</code></td>
			<td>Enable Garnet (Redis-compatible cache).</td>
		</tr>
		<tr>
			<td>garnet-instance.statefulSet.replicas</td>
			<td>int</td>
			<td><code>`1`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>garnet-instance.persistence.enabled</td>
			<td>bool</td>
			<td><code>`true`</code></td>
			<td>Enable PVC for Garnet data.</td>
		</tr>
		<tr>
			<td>garnet-instance.volumeClaimTemplates.storageClassName</td>
			<td>string</td>
			<td><code>`""`</code></td>
			<td>Use default StorageClass if unset (official chart default is local-storage).</td>
		</tr>
		<tr>
			<td>garnet-instance.volumeClaimTemplates.requestsStorage</td>
			<td>string</td>
			<td><code>`"1Gi"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>garnet-instance.resources.requests.cpu</td>
			<td>string</td>
			<td><code>`"20m"`</code></td>
			<td></td>
		</tr>
		<tr>
			<td>garnet-instance.resources.requests.memory</td>
			<td>string</td>
			<td><code>`"64Mi"`</code></td>
			<td></td>
		</tr>
	</tbody>
</table>

## Dependencies

## Requirements

Kubernetes: `>=1.25.0-0`

| Repository | Name | Version |
|------------|------|---------|
| https://cloudnative-pg.github.io/charts | postgresql-operator(cloudnative-pg) | ^0.27.0 |
| https://cloudnative-pg.github.io/charts | postgresql-instance(cluster) | ^0.5.0 |
| https://grafana.github.io/helm-charts | grafana(grafana) | ^10.0.0 |
| https://grafana.github.io/helm-charts | loki(loki) | ^6.0.0 |
| https://grafana.github.io/helm-charts | mimir(mimir-distributed) | ^5.8.0 |
| https://grafana.github.io/helm-charts | tempo(tempo) | ^1.20.0 |
| https://seaweedfs.github.io/seaweedfs/helm | seaweedfs-instance(seaweedfs) | ^4.0.0 |
| oci://ghcr.io/microsoft/helm-charts | garnet-instance(garnet) | 0.2.2 |

## License

Apache-2.0 (umbrella; subcharts retain their own licenses).
