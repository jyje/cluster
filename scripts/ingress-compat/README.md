# ingress-nginx to Higress compatibility tests

Scripts for the evaluation tracked in #314. Each script sends the same requests
through ingress-nginx and Higress and prints what each controller does, so the
comparison can be repeated instead of argued from documentation.

The tests are read-only for the cluster. They start `kubectl port-forward` and
call hosts that do not resolve (`*.compat.invalid`). The test backends and
Ingresses are defined in `clusters/r4spi/apps/higress.yaml`, and the
`higress` Argo CD Application has to be synced for them to exist.

## compat.py: long connections and default timeouts

```bash
scripts/ingress-compat/compat.py --context microk8s
```

For five Ingress variants (ingress-nginx and Higress, with and without a
timeout annotation) it runs three tests at the same time:

| Test | What it checks |
|---|---|
| response delayed | One response that arrives after 75 seconds with nothing sent before it |
| streamed 1 byte/s | A response that sends one byte a second for 90 seconds, like SSE |
| idle WebSocket | A WebSocket idle for 75 seconds, then used again |

The default hold of 75 seconds is above the 60 second ingress-nginx default, so
a controller that keeps its default shows up as FAIL. Use `--hold` to change it
and `--json` to keep the raw results. It needs `kubectl` and Python 3.9 or
later, and uses only the standard library.
