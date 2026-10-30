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

The owner (jyje) is always an authentik superuser. A sealed blueprint,
`authentik-owner` in [`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml),
keeps the account in `AuthentikAdmin`, so nobody has to promote it by hand in the
admin interface.

- **It matches by verified email, not by username.** The username is chosen
  during Google enrollment, so a username match would hand the role to whoever
  takes a free `jyje`. The email is the owner's, which only the owner's Google
  login can present. It lives in the sealed blueprint, so it is not in the public
  file.
- **If the account is missing, the blueprint creates it** with the owner's
  email. The first Google sign-in with that email attaches to it, because the
  source links accounts by email. The owner then has the role without anything
  else to do.
- **If the owner enrolls first,** the new account lands in `Unknown`, and the next
  time the blueprint is applied it finds the account by email and promotes it.
  A sign-in does not trigger an apply. authentik finds new and changed blueprint
  files in a discovery task that runs about once an hour. After the merge that
  added `authentik-owner`, the new worker did not pick the file up at start, and
  the owner was promoted about 30 minutes later, when that task ran. To promote
  at once, apply the blueprint instance again in the admin interface (System,
  Blueprints). A file that has no instance yet only appears after a discovery
  run.
- **The account type must be `internal`.** Accounts made by the Google
  enrollment flow are `external`, and the admin interface refuses them with
  "Interface can only be accessed by internal users", even for a superuser. The
  blueprint sets `type: internal` on the owner. Until that is applied the owner
  cannot open the admin interface to apply it by hand, so it waits for the next
  discovery run.
- The `groups` list replaces the user's direct memberships. The lower groups
  still apply through the hierarchy.
- It depends on two assumptions about the Google source: it returns only
  verified emails, and the enrollment flow does not let a person type their own
  email. Check both before relying on this for anything beyond the owner.
- Other people are never promoted by the blueprint. Add them in the admin
  interface (Directory, Users, the user, Groups), or put them in a sealed
  blueprint on purpose.
- To change the owner's email, reseal the blueprint (see
  [introduction.md](../introduction.md#secrets)) and replace
  `authentik-owner` in `authentik.yaml`.

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
| The owner is not a superuser after signing in | The owner enrolled before the blueprint was applied, or the blueprint is new and the hourly discovery has not run yet, so the account is in `Unknown`. Wait for the next discovery, or apply the blueprint instance again (System, Blueprints). If it fails with "multiple users", two accounts share the owner's email and one has to be removed. |
| The admin interface says "Interface can only be accessed by internal users" | The account is type `external`. The owner blueprint sets `internal`. For any other admin, change the type in the admin interface (Directory, Users) or in a sealed blueprint on purpose. |
| Sign-in answers `invalid_request` | The OAuth2 provider has no `grant_types`. See rule 3. |
