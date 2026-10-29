# authentik access: who gets in, and what a new app must do

[한국어](authentik-access-ko.md)

The owner account is always an authentik superuser, and every application
blueprint has to let that account in. This page explains both so a new
application does not end up with a "Permission denied" screen after sign-in.

## Groups

Groups are defined in the `authentik-rbac-groups` blueprint in
[`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml). A group inherits
from its parents, so a member of a lower group also counts as a member of every
group above it in this list.

| Group | Parent | Superuser | Meaning |
| --- | --- | --- | --- |
| `Unknown` | none | no | Every new Google sign-in lands here with no permissions. |
| `Viewer` | `Unknown` | no | Read only access. |
| `Developer` | `Viewer` | no | Day to day use. |
| `AuthentikAdmin` | `Developer` | **yes** | Administers authentik. |
| `ClusterAdmin` | `AuthentikAdmin` | **yes** | Also the top tier in Argo CD. |

## The owner is promoted automatically

The blueprint puts `jyje` in `AuthentikAdmin`, so the owner does not have to be
promoted by hand in the admin interface. authentik applies the blueprint when its
file changes. A sign-in does not trigger it.

- The account itself still comes from the Google enrollment flow. A new
  account lands in `Unknown` first and is promoted when the blueprint is next
  applied. To promote it right away, apply the blueprint instance again in the
  admin interface (System, Blueprints).
- The `groups` list in a blueprint replaces the user's direct memberships. The
  lower groups still apply through the hierarchy.
- If the account is deleted, the blueprint recreates it empty, and Google
  sign-in has nothing to attach to (the source links accounts by email). Sign in
  with another admin and fix it by hand, or add the email to the blueprint.
- Other people are never promoted by the blueprint. Add them in the admin
  interface (Directory, Users, the user, Groups) or by listing them in a
  blueprint on purpose.

## Rule for every new application

Binding an application to a group is how access is decided. **Superusers are
not admitted automatically**, so a new application that binds only a narrow
group would lock out the owner. Every application blueprint must therefore:

1. **Keep a binding for `AuthentikAdmin`.** This is how the owner gets in, and
   it also admits `ClusterAdmin`.
2. Add narrower groups only as extra bindings. An application is opened when any
   binding matches.
3. Set what the provider needs. For an OAuth2/OpenID provider created from a
   blueprint that includes `grant_types` (for example
   `authorization_code` and `refresh_token`), the redirect URIs and a signing
   key. Without `grant_types` sign-in fails with `invalid_request`.
4. Check it as the owner before calling it done: open the application and sign
   in. A "Permission denied" screen after a successful login means the binding
   is missing or too narrow.

```yaml
- model: authentik_policies.policybinding
  identifiers:
    target: !KeyOf my-app
    order: 0
  attrs:
    group: !Find [authentik_core.group, [name, AuthentikAdmin]]
```

A complete example is
[`examples/hermes-dashboard-blueprint.yaml`](examples/hermes-dashboard-blueprint.yaml),
and the Hermes specific steps are in [hermes-dashboard.md](hermes-dashboard.md).

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| "Permission denied" right after a successful sign-in | The account is not in a group bound to the application. Add the `AuthentikAdmin` binding, or put the user in the group. |
| The owner is not a superuser after a fresh install | The account did not exist yet when the blueprint was applied. Sign in once through Google, then apply the blueprint instance again (System, Blueprints). |
| Sign-in answers `invalid_request` | The OAuth2 provider has no `grant_types`. See rule 3. |
