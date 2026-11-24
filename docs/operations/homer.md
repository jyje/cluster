# Homer dashboard

The start page at `https://app.jyje.online` is a Homer dashboard. It is made by the homer-operator from one `Dashboard` resource, and every card is written by hand in that resource. Automatic discovery is off.

## Where it lives

| Part | Location |
| :-- | :-- |
| Operator | Application `homer-operator` |
| Dashboard resource and cards | `clusters/r4spi/apps/homer-instance.yaml`, the `Dashboard` named `homer`, under `homerConfig.services` |
| Namespace | `homer-instance` |

## Add or change a card

Edit `homerConfig.services` in `homer-instance.yaml`. A card is an item in one of the groups:

```yaml
- parameters:
    name: "Airflow"
    logo: "https://example.com/logo.svg"
    subtitle: "Workflow scheduler"
    tag: "airflow #workflow #dag"
    url: "https://airflow.app.jyje.online"
    type: "Ping"
```

- `type: "Ping"` shows a status dot. Without `endpoint` the dashboard requests `url`. Set `endpoint` (and `method: "GET"` if the check needs it) when the root page is not a good health signal, for example when it answers 404 or needs a login. The check runs in the browser, so the endpoint must allow the dashboard origin.
- Tags follow one pattern: the app name first, then two to four words that describe it, for example `n8n #workflow #automation #cicd`.
- Items sort by name inside a group. `order: "-1"` moves a card to the bottom, and it needs homer-operator 1.2.4.
- Group names carry a number (`1. Applications`, `2. Dashboards`, `3. Management`, `4. External Links`). The operator sorts groups by name, so the number is the only way to set their order. To add a card to a group, use its exact name.

The Application values live in the Application, so after merging a change, sync `apps` first and then `homer-instance`.

## Automatic discovery is off

The operator can build cards from Ingress annotations (`item.homer.rajsingh.info/*`). This cluster does not use that any more.

Why it was turned off:

- The Ingresses to read were chosen by an allow list of `app.kubernetes.io/name` values in `ingressSelector`. Each new app needed a change in two places, and an app that was not on the list never showed up. Airflow was missed this way.
- A list of names does not help to keep the dashboard accurate, and almost every card was curated by hand anyway.

How it is turned off:

- The operator has no switch for discovery, and an unset selector means "match everything". So `ingressSelector` and `httpRouteSelector` both match the label `homer.jyje.online/discovery: enabled`. Nothing carries that label, so nothing is discovered.
- Services are only discovered when `serviceSelector` is set, and it is not set.

The Homer annotations that are still on the Ingresses of the apps are ignored. They are harmless and are kept as a record of the card text.

To discover an Ingress again, give it the label `homer.jyje.online/discovery: enabled` and its `item.homer.rajsingh.info/*` and `service.homer.rajsingh.info/name` annotations. A discovered card with the same group name is merged into the manual group. Do not also keep a manual card for it, or the card shows twice.

## Checks after a change

- Argo CD shows `homer-instance` as Synced and Healthy.
- The rendered configuration has the cards you expect:

  ```bash
  kubectl -n homer-instance get cm homer-homer -o jsonpath='{.data.config\.yml}'
  ```

- Open the dashboard and check the new card, its link and its status dot.
