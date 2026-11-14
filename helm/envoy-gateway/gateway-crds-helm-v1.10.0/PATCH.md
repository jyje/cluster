# Local patch

The upstream chart does not provide a value for injecting arbitrary manifests.
This repository adds the optional `extraResources` value and its rendering
template. The list defaults to empty, so the patch does not change the default
rendered resources.
