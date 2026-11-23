# Local patch

- Source: `https://airflow.apache.org` chart `airflow` 1.22.0 (`appVersion` 3.2.2)
- Tracking issue: #405
- Add the standard `extraResources` key: `templates/extra-resources.yaml`, the value in `values.yaml` and the schema property in `values.schema.json`. Nothing else differs from upstream.
- The chart still defaults to Airflow 3.2.2 and `CeleryExecutor`. The Application sets the Airflow version, the image tag and the executor explicitly.
