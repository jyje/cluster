# Local patches

- Add the optional root `extraResources` hook.
- Use the schema from the packaged `common` 30.4.5 dependency and add
  validation for `extraResources` so Helm works without a remote schema.
  No dependency files are modified.

- Provider: `truecharts-factorio`
- Source: `oci://oci.trueforge.org/truecharts/factorio`
- OCI digest: `sha256:c9212706bbef806014237761d323dcf009b191be8a3d960fb77621ef5e1a83b8`
