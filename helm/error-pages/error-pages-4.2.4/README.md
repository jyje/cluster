## Installing the chart

```shell
# Install a specific version
helm install error-pages oci://ghcr.io/tarampampam/error-pages/charts/error-pages \
  --version 4.2.4

# Install with custom values file
helm install error-pages oci://ghcr.io/tarampampam/error-pages/charts/error-pages \
  --version 4.2.4 \
  --values my-values.yaml
```

## Upgrading

```shell
helm upgrade error-pages oci://ghcr.io/tarampampam/error-pages/charts/error-pages
```

## Use cases

### ingress-nginx - default backend

Route all unhandled error responses through error-pages when using [ingress-nginx](https://kubernetes.github.io/ingress-nginx/).

`values.yaml`:

```yaml
config:
  sendSameHttpCode: true
```

For more details, please, refer to the [project's documentation](https://github.com/tarampampam/error-pages#readme).

### Traefik - errors middleware

Use the built-in `traefikMiddleware` to let [Traefik](https://doc.traefik.io/traefik/) intercept error responses
and forward them to error-pages.

`values.yaml`:

```yaml
traefikMiddleware:
  enabled: true # creates a Middleware CRD in the same namespace
  #statusCodes: ["400-599"]
  #query: "/{status}"
```

For more details, please, refer to the [project's documentation](https://github.com/tarampampam/error-pages#readme).

### Template rotation

Serve a different built-in HTML template on each request (great for a bit of personality in staging environments):

```yaml
config:
  htmlTemplate:
    rotationMode: random-on-each-request
```

### Custom HTML template

Load a custom Go template from a ConfigMap volume, a URL, or inline text:

```yaml
# Inline template (small templates only)
config:
  htmlTemplate:
    custom: |
      <!DOCTYPE html>
      <html>
        <body><h1>{{ .StatusCode }} - {{ .Message }}</h1></body>
      </html>
```

```yaml
# From a URL fetched once at startup
config:
  htmlTemplate:
    custom: "https://example.com/my-error-template.html"
```

```yaml
# From a file mounted into the pod
deployment:
  volumes:
    - name: templates
      configMap:
        name: my-error-templates
  volumeMounts:
    - name: templates
      mountPath: /templates
      readOnly: true

config:
  htmlTemplate:
    custom: "/templates/error.html"
```

### Custom HTTP status codes

Override descriptions or add non-standard codes (e.g. `499`, `4**` wildcard):

```yaml
config:
  addCode:
    - {code: "4**", message: "Client Error", description: "Something went wrong on the client side"}
    - code: "499"
      message: "Client Closed Request"
      description: "The client closed the connection before the server finished responding"
```

Via `--set` (`--set-string` is required for numeric-looking codes like `499`):

```shell
helm install error-pages oci://ghcr.io/tarampampam/error-pages/charts/error-pages \
  --set-string 'config.addCode[0].code=4**' \
  --set 'config.addCode[0].message=Client Error' \
  --set-string 'config.addCode[1].code=499' \
  --set 'config.addCode[1].message=Client Closed Request' \
  --set 'config.addCode[1].description=The client closed the connection before the server finished responding'
```

### Adding extra links

Display additional links (status page, contact, privacy policy, etc.) on all error pages:

```yaml
config:
  addLink:
    - {label: "Status Page", url: "https://status.example.com"}
    - {label: "Contact Support", url: "https://example.com/contact"}
    - {label: "Privacy Policy", url: "https://example.com/privacy"}
```

Via `--set`:

```shell
helm install error-pages oci://ghcr.io/tarampampam/error-pages/charts/error-pages \
  --set 'config.addLink[0].label=Status Page' \
  --set 'config.addLink[0].url=https://status.example.com' \
  --set 'config.addLink[1].label=Contact Support' \
  --set 'config.addLink[1].url=https://example.com/contact'
```

## 💊 Support

If you need a chart option that doesn't exist yet, or something isn't working as expected, please
[open an issue](https://github.com/tarampampam/error-pages/issues/new/choose) - I'll be happy to help.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| config.addCode | []object/null | *all built-in codes* | Add or override HTTP status codes. Each entry must have `code` and `message` (required), and optionally `description`. `code` supports wildcards like `4**`. |
| config.addLink | []object/null | `nil` | Extra links to display on error pages. Each entry must have `label` and `url` (both required). |
| config.defaultErrorPage | integer/null | `404` | Default HTTP status code to render when the requested code is not found or the path is not a valid code |
| config.disableBuiltInCodes | bool/null | `nil` | Disable built-in HTTP status code descriptions |
| config.disableL10n | bool/null | `nil` | Disable client-side localization of error pages |
| config.homepageUrl | string/null | `nil` | Homepage URL to show as a link in error pages (e.g. https://app.example.com/home). When set, supported templates display a "Go to homepage" link pointing to this URL. |
| config.htmlTemplate.custom | string/null | `nil` | Custom HTML template (inline *Go template* text, *URL*, or *file path*). **When set, `name` and `rotationMode` are ignored by the application**. |
| config.htmlTemplate.name | string/null | `app-down` | Built-in HTML template name (**ignored when `custom` is set**). Available: `app-down`, `cats`, `connection`, `ghost`, `hacker-terminal`, `l7`, `lost-in-space`, `noise`, `orient`, `shuffle`, `win98`. For full list of built-in templates and their appearance, see the [repository's README](https://github.com/tarampampam/error-pages#readme) |
| config.htmlTemplate.rotationMode | string/null | `disabled` | Template rotation mode (**ignored when `custom` is set**). Available: `disabled`, `random-on-startup`, `random-on-each-request`, `random-hourly`, `random-daily` |
| config.jsonTemplate.custom | string/null | `nil` | Custom JSON template (inline *Go template* text, *URL*, or *file path*). Set to `null` to use the built-in JSON template. |
| config.listen.address | string/null | `0.0.0.0` | IP (v4 or v6) address to listen on (`0.0.0.0` to bind to all interfaces) |
| config.listen.port | int | `8080` | HTTP server port |
| config.log.format | string/null | `json` (defined in the Dockerfile) | Logging format - `console` / `json` |
| config.log.level | string/null | `info` (defined in the Dockerfile) | Logging level - `debug` / `info` / `warn` / `error` |
| config.proxyHeaders | []string/null | `X-Request-Id`, `X-Trace-Id`, `X-Correlation-Id`, `X-Amzn-Trace-Id` | List of HTTP headers to proxy from the original request to the error page context (no spaces in names). Set to `null` to leave unset, or set to `[]` (empty list) to disable proxy headers entirely. |
| config.sendSameHttpCode | bool/null | `false` | Reply with the same HTTP status code as the requested error page instead of always returning 200. **Should be enabled when used as ingress-nginx defaultBackend and other controllers/gateways where the client relies on the actual HTTP status code to detect an error page**. |
| config.showDetails | bool/null | `false` | Show request details (`X-Original-URI`, `X-Namespace`, etc.) on the error page (template-dependent) |
| config.txtTemplate.custom | string/null | `nil` | Custom plain-text template (inline *Go template* text, *URL*, or *file path*). Set to `null` to use the built-in plain-text template. |
| config.xmlTemplate.custom | string/null | `nil` | Custom XML template (inline *Go template* text, *URL*, or *file path*). Set to `null` to use the built-in XML template. |
| deployment.affinity | object | `{}` | Affinity for pod assignment (supports templating), more information can be [found here](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) |
| deployment.args | list | `[]` | The list of additional arguments to pass to the container (supports templating) |
| deployment.enabled | bool | `true` | Enable deployment (`deployment.yaml` is not rendered when disabled) |
| deployment.env | list | `[]` | The list of additional environment variables to set in the container (supports templating) |
| deployment.imagePullSecrets | list | `[]` | This is for the secrets for pulling an image from a private repository (supports templating), more information can be [found here](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/) |
| deployment.labels | object | `{}` | Additional deployment labels (e.g. for filtering deployment by custom labels; supports templating) |
| deployment.nodeSelector | object | `{}` | Node selector for pod assignment (supports templating), more information can be [found here](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) |
| deployment.podAnnotations | object | `{}` | Additional pod annotations (e.g. for mesh injection or Prometheus scraping, supports templating). More information can be [found here](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/) |
| deployment.probe.initialDelay | int | `2` | Number of seconds after the container has started before liveness probes are initiated |
| deployment.probe.interval | int | `10` | How often (in seconds) to perform the probe |
| deployment.replicas | int | `1` | How many replicas to run |
| deployment.resources | object | *memory: 32/64Mi* | Resource limits and requests, more information can be [found here](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) |
| deployment.securityContext | object | *non-root, read-only fs, no privilege escalation* | Security context for the pod, more information can be [found here](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/#security-context-1). |
| deployment.tolerations | list | `[]` | Tolerations for pod assignment, more information can be [found here](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/) |
| deployment.volumeMounts | list | `[]` | Additional volumeMounts to add to the container (supports templating) |
| deployment.volumes | list | `[]` | Additional volumes to add to the pod, more information can be [found here](https://kubernetes.io/docs/concepts/storage/volumes/) |
| fullnameOverride | string/null | `nil` | The name of the Helm release |
| image.pullPolicy | string | `"IfNotPresent"` | Defines the image pull policy |
| image.repository | string | `"ghcr.io/tarampampam/error-pages"` | The image repository to pull from |
| image.tag | string/null | `nil` | Overrides the image tag whose default is the chart appVersion |
| nameOverride | string/null | `nil` | This is to override the chart name |
| namespaceOverride | string/null | `nil` | Override the default Release Namespace for Helm |
| service.annotations | object | `{}` | Additional service annotations (e.g. for MetalLB, monitoring or service discovery, supports templating). |
| service.enabled | bool | `true` | Enable service (`service.yaml` is not rendered when disabled) |
| service.loadBalancerSourceRanges | list | `[]` | Limit access to the load balancer to specific CIDR ranges. Works only with type: LoadBalancer. |
| service.port | int | `8080` | Sets the port, more information can be [found here](https://kubernetes.io/docs/concepts/services-networking/service/#field-spec-ports) |
| service.type | string | `"ClusterIP"` | Sets the service type more information can be [found here](https://kubernetes.io/docs/concepts/services-networking/service/#publishing-services-service-types) |
| traefikMiddleware.enabled | bool | `false` | Create a Traefik Middleware CRD that routes error responses to this service (`middleware.yaml` is not rendered when disabled). More information can be [found here](https://doc.traefik.io/traefik/middlewares/http/errorpages/) |
| traefikMiddleware.query | string | `"/{status}"` | Query path pattern passed to Traefik's errors middleware. The {status} placeholder is replaced    by Traefik with the actual HTTP status code before forwarding the request to this service. |
| traefikMiddleware.statusCodes | list | `["400-599"]` | HTTP status codes (or ranges) that Traefik will intercept and forward to error-pages.    Each entry can be a single code ("404") or a range ("400-599"). |
| traefikMiddleware.statusRewrites | map/null | `nil` | Optional map of status code rewrites to apply before Traefik forwards the request.    Whatever is set here is placed into the manifest as-is (supports templating).    Example:      statusRewrites:        "400-499": 400        "500-599": 500 |
